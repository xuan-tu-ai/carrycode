"""Offline test doubles for runtime roles."""

from __future__ import annotations

import json

from carrycode.llm import RoleLLM


class ScriptedRoleLLM(RoleLLM):
    """Returns queued replies in order. A dict reply is sent as JSON text. Raises RuntimeError when empty."""

    def __init__(self, replies: list[str | dict], max_retries: int = 1) -> None:
        super().__init__(model_name="scripted", max_retries=max_retries)
        self.replies: list[str | dict] = list(replies)
        self.requests: list[list[dict]] = []

    def _call(self, messages: list[dict]) -> str:
        self.requests.append([dict(m) for m in messages])
        self.usage.calls += 1
        if not self.replies:
            raise RuntimeError("ScriptedRoleLLM: no replies left")
        reply = self.replies.pop(0)
        return reply if isinstance(reply, str) else json.dumps(reply)
