"""Offline end-to-end fold: scripted runtime roles over mini-swe-agent tool-call messages."""

import json

import yaml
from minisweagent.config import builtin_config_dir
from minisweagent.environments.local import LocalEnvironment
from minisweagent.models.test_models import DeterministicToolcallModel, make_toolcall_output

from carrycode.agent import CarryOnAgent
from carrycode.compiler import Compiler
from carrycode.metrics import trajectory_usage
from carrycode.records import CarrierType
from carrycode.registry import make_carrier_id
from carrycode.runtime import CarryOnRuntime
from carrycode.testing import ScriptedRoleLLM
from carrycode.tracker import Tracker

AGENT_CONFIG = yaml.safe_load((builtin_config_dir / "default.yaml").read_text())["agent"]

FINISH = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\necho done"

TRACKER_REPLY = {
    "candidate_updates": [
        {
            "candidate_id": "C1",
            "provisional_type": "information_product",
            "subject": "echo output",
            "description": "what echo printed",
            "supporting_steps": [3],
            "first_seen_step": 2,
            "last_revised_step": 3,
        }
    ],
    "compile_requests": [{"candidate_id": "C1", "evidence_steps": [3]}],
}

COMPILER_REPLY = {
    "carrier_edits": [
        {
            "candidate_id": "C1",
            "carrier_type": "information_product",
            "subject": "echo output",
            "summary": "echo a printed a",
            "claims": [{"claim_id": "K1", "proposition": "echo a prints a", "source_steps": [3]}],
        }
    ],
    "execution_context": {"current_focus": ["continue"]},
}


class RecordingToolcallModel(DeterministicToolcallModel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.seen: list[list[dict]] = []

    def query(self, messages, **kwargs):
        self.seen.append(list(messages))
        return super().query(messages, **kwargs)


def tc(i: int, command: str) -> dict:
    call_id = f"call_{i}"
    tool_call = {
        "id": call_id,
        "type": "function",
        "function": {"name": "bash", "arguments": json.dumps({"command": command})},
    }
    return make_toolcall_output(f"step {i}", [tool_call], [{"command": command, "tool_call_id": call_id}])


def assert_tool_pairs_ok(view: list[dict]) -> None:
    """Every tool message follows (through other tool messages only) an assistant message that issued its id."""
    open_ids: set[str] = set()
    for message in view:
        role = message.get("role")
        if role == "assistant":
            open_ids = {call["id"] for call in message.get("tool_calls") or []}
        elif role == "tool":
            assert message.get("tool_call_id") in open_ids, f"orphaned tool result: {message.get('tool_call_id')}"
            open_ids.discard(message["tool_call_id"])
        else:
            open_ids = set()


def test_fold_end_to_end_with_tool_calls():
    m = RecordingToolcallModel(outputs=[tc(0, "echo a"), tc(1, "echo b"), tc(2, "echo c"), tc(3, FINISH)])
    rt = CarryOnRuntime(
        Tracker(ScriptedRoleLLM([TRACKER_REPLY])),
        Compiler(ScriptedRoleLLM([COMPILER_REPLY])),
        trigger_tokens=1,
    )
    agent = CarryOnAgent(m, LocalEnvironment(), runtime=rt, **AGENT_CONFIG)

    info = agent.run("do things")

    assert info["exit_status"] == "Submitted"
    assert [msg["role"] for msg in agent.messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
        "tool",
        "assistant",
        "exit",
    ]
    assert rt.stats.attempts == 3
    assert rt.stats.committed == 1
    assert agent.fold_index == 4

    carrier = rt.store.get(make_carrier_id(CarrierType.INFORMATION_PRODUCT, "echo output"))
    assert carrier.claims[0].source_steps == [3]

    assert len(m.seen) == 4
    assert len(m.seen[0]) == 2
    assert len(m.seen[1]) == 3
    for k in range(1, 4):
        assert m.seen[k][2]["content"].startswith("<carryon_checkpoint>")
        assert m.seen[k][:2] == agent.messages[:2]
        assert m.seen[k][3:] == agent.messages[4 : 4 + len(m.seen[k]) - 3]
    for view in m.seen:
        assert_tool_pairs_ok(view)

    usage = trajectory_usage(agent.serialize())
    assert usage.folds_committed == 1
    assert usage.folds_attempted == 3
