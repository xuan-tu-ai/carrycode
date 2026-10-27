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
from carrycode.view import estimate_tokens

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


def test_fold_with_keep_recent_tokens_retains_live_tail():
    m = RecordingToolcallModel(
        outputs=[
            tc(0, "echo step0-padding-" + "a" * 40),
            tc(1, "echo step1-padding-" + "b" * 40),
            tc(2, "echo step2"),
            tc(3, FINISH),
        ]
    )
    rt = CarryOnRuntime(
        Tracker(ScriptedRoleLLM([TRACKER_REPLY])),
        Compiler(ScriptedRoleLLM([COMPILER_REPLY])),
        trigger_tokens=1,
        keep_recent_tokens=25,
    )
    agent = CarryOnAgent(m, LocalEnvironment(), runtime=rt, **AGENT_CONFIG)

    info = agent.run("do things")

    assert info["exit_status"] == "Submitted"
    assert rt.stats.committed == 1
    # After commit, fold_index points at start of kept suffix (step 1 assistant at index 4)
    assert agent.fold_index == 4
    # The kept suffix starts with an assistant message (never tool)
    assert agent.messages[agent.fold_index]["role"] == "assistant"

    # Trigger baseline after commit equals token estimate of kept suffix
    kept_suffix = agent.messages[agent.fold_index : 6]  # step 1 asst + tool
    assert rt.trigger_baseline == estimate_tokens(kept_suffix)
    assert rt.trigger_baseline > 0

    # Every view passes tool-pair check
    for view in m.seen:
        assert_tool_pairs_ok(view)

    # Views after fold commit (views 2 and 3)
    for k in range(2, 4):
        assert m.seen[k][2]["content"].startswith("<carryon_checkpoint>")
        assert m.seen[k][:2] == agent.messages[:2]
        # view[3:] equals agent.messages[fold_index:...]
        assert m.seen[k][3:] == agent.messages[agent.fold_index : agent.fold_index + len(m.seen[k]) - 3]


def test_rejected_fold_leaves_fold_index_unchanged():
    m = RecordingToolcallModel(
        outputs=[
            tc(0, "echo a"),
            tc(1, FINISH),
        ]
    )
    rejected_tracker = {"candidate_updates": [], "compile_requests": [], "resolved_obligation_ids": []}
    rt = CarryOnRuntime(
        Tracker(ScriptedRoleLLM([rejected_tracker])),
        Compiler(ScriptedRoleLLM([])),
        trigger_tokens=1,
        keep_recent_tokens=0,
    )
    agent = CarryOnAgent(m, LocalEnvironment(), runtime=rt, **AGENT_CONFIG)
    initial_fold_index = agent.fold_index  # 2

    info = agent.run("do things")

    assert info["exit_status"] == "Submitted"
    assert rt.stats.attempts == 1
    assert rt.stats.committed == 0
    assert agent.fold_index == initial_fold_index


def test_keep_recent_tokens_zero_reproduces_old_behaviour():
    m = RecordingToolcallModel(outputs=[tc(0, "echo a"), tc(1, FINISH)])
    rt = CarryOnRuntime(
        Tracker(ScriptedRoleLLM([TRACKER_REPLY])),
        Compiler(ScriptedRoleLLM([COMPILER_REPLY])),
        trigger_tokens=1,
        keep_recent_tokens=0,
    )
    agent = CarryOnAgent(m, LocalEnvironment(), runtime=rt, **AGENT_CONFIG)

    info = agent.run("do things")

    assert info["exit_status"] == "Submitted"
    assert rt.stats.committed == 1
    # With keep_recent_tokens=0, fold_index equals the message count at fold commit (4)
    assert agent.fold_index == 4
    assert rt.trigger_baseline == 0
