"""Tests for RoleLLM test seam and ScriptedRoleLLM."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from carrycode.llm import RoleLLM
from carrycode.testing import ScriptedRoleLLM


class Foo(BaseModel):
    x: int


def test_valid_reply_is_parsed() -> None:
    llm = ScriptedRoleLLM([{"x": 1}])
    result = llm.complete_json("s", "u", Foo)
    assert result == Foo(x=1)
    assert llm.usage.calls == 1


def test_invalid_json_is_retried() -> None:
    llm = ScriptedRoleLLM(["not json", '{"x": 2}'])
    result = llm.complete_json("s", "u", Foo)
    assert result == Foo(x=2)
    assert llm.usage.calls == 2
    assert len(llm.usage.failures) == 1
    assert len(llm.requests[1]) == 4
    assert llm.requests[1][-1]["role"] == "user"
    assert "Invalid output" in llm.requests[1][-1]["content"]


def test_schema_violation_is_retried() -> None:
    llm = ScriptedRoleLLM([{"y": 1}, {"x": 3}])
    result = llm.complete_json("s", "u", Foo)
    assert result == Foo(x=3)


def test_none_after_retries() -> None:
    llm = ScriptedRoleLLM(["bad", "bad"], max_retries=1)
    result = llm.complete_json("s", "u", Foo)
    assert result is None
    assert llm.usage.calls == 2


def test_empty_script_raises() -> None:
    llm = ScriptedRoleLLM([])
    with pytest.raises(RuntimeError):
        llm.complete_json("s", "u", Foo)


def test_real_call_path_uses_litellm(monkeypatch) -> None:
    import litellm

    received_kwargs: dict = {}

    def fake(**kwargs):
        received_kwargs.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"x": 5}'))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2),
        )

    def fake_cost(**kwargs):
        raise ValueError("price table error")

    monkeypatch.setattr(litellm, "completion", fake)
    monkeypatch.setattr(litellm, "completion_cost", fake_cost)

    llm = RoleLLM("m")
    result = llm.complete_json("s", "u", Foo)
    assert result == Foo(x=5)
    assert llm.usage.input_tokens == 10
    assert llm.usage.output_tokens == 2
    assert llm.usage.cost == 0.0
    assert received_kwargs.get("response_format") == {"type": "json_object"}
