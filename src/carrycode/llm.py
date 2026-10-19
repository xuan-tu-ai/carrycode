"""JSON-output LLM calls for the runtime roles (Tracker, Compiler), via LiteLLM."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


@dataclass
class RoleUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    failures: list[str] = field(default_factory=list)


class RoleLLM:
    """One runtime role bound to one model. Counts usage so runtime overhead can be reported."""

    def __init__(self, model_name: str, model_kwargs: dict | None = None, max_retries: int = 1) -> None:
        self.model_name = model_name
        self.model_kwargs = model_kwargs or {}
        self.max_retries = max_retries
        self.usage = RoleUsage()

    def complete_json(self, system: str, user: str, schema: type[T]) -> T | None:
        """Ask for a JSON object matching `schema`. Returns None after repeated invalid output."""
        import litellm  # imported lazily so offline tests do not need it

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for _ in range(self.max_retries + 1):
            response = litellm.completion(
                model=self.model_name,
                messages=messages,
                response_format={"type": "json_object"},
                **self.model_kwargs,
            )
            self._record(response, litellm)
            text = response.choices[0].message.content or ""
            try:
                return schema.model_validate(json.loads(text))
            except (json.JSONDecodeError, ValidationError) as e:
                self.usage.failures.append(str(e)[:300])
                messages += [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"Invalid output: {e}. Reply with corrected JSON only."},
                ]
        return None

    def _record(self, response, litellm) -> None:
        self.usage.calls += 1
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.usage.input_tokens += getattr(usage, "prompt_tokens", 0) or 0
            self.usage.output_tokens += getattr(usage, "completion_tokens", 0) or 0
        try:
            self.usage.cost += litellm.completion_cost(completion_response=response)
        except Exception:
            pass  # model missing from LiteLLM's price table; tokens are still counted
