"""CarryOnAgent end to end with mini-swe-agent's deterministic model and a local shell."""

import json

import yaml
from minisweagent.config import builtin_config_dir
from minisweagent.environments.local import LocalEnvironment
from minisweagent.models.test_models import DeterministicModel, make_output

from carrycode.agent import CarryOnAgent, SlidingWindowAgent, split_live_tail
from carrycode.metrics import trajectory_usage
from carrycode.records import CarrierRecord, CarrierType
from carrycode.runtime import CarryOnRuntime

AGENT_CONFIG = yaml.safe_load((builtin_config_dir / "default.yaml").read_text())["agent"]
FINISH = "echo 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT'\necho done"


class RecordingModel(DeterministicModel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.seen: list[list[dict]] = []

    def query(self, messages, **kwargs):
        self.seen.append(list(messages))
        return super().query(messages, **kwargs)


def model(n_steps: int) -> RecordingModel:
    outputs = [make_output(f"step {i}", [{"command": f"echo step{i}"}]) for i in range(n_steps)]
    return RecordingModel(outputs=[*outputs, make_output("finish", [{"command": FINISH}])])


class FakeRuntime(CarryOnRuntime):
    """Commits one carrier on the first fold attempt; no LLM calls."""

    def __init__(self):
        super().__init__(tracker=None, compiler=None, trigger_tokens=1)

    def fold(self, task, live_tail, log_offset, env) -> bool:
        if self.stats.committed:
            return False
        self.store.apply(
            [
                CarrierRecord(
                    carrier_id="f1",
                    carrier_type=CarrierType.EXTERNAL_OBJECT,
                    subject="src/a.py",
                    summary="patched",
                    committed_at_fold=1,
                )
            ]
        )
        self.stats.committed += 1
        return True


class CountingRuntime(CarryOnRuntime):
    def __init__(self):
        super().__init__(tracker=None, compiler=None, trigger_tokens=1)
        self.fold_calls = 0

    def fold(self, task, live_tail, log_offset, env) -> bool:
        self.fold_calls += 1
        return False


def test_carryon_agent_sends_view_but_keeps_full_log():
    m = model(3)
    agent = CarryOnAgent(m, LocalEnvironment(), runtime=FakeRuntime(), **AGENT_CONFIG)
    info = agent.run("do things")
    assert info["exit_status"] == "Submitted"
    # The first fold fires on the second query (the tail is empty on the first one).
    last_view = m.seen[-1]
    assert any("<carryon_checkpoint>" in str(msg.get("content")) for msg in last_view)
    assert len(last_view) < len(agent.messages)  # the model saw less than the full log
    assert agent.messages[0]["role"] == "system"


def test_trajectory_contains_carryon_state():
    agent = CarryOnAgent(model(3), LocalEnvironment(), runtime=FakeRuntime(), **AGENT_CONFIG)
    agent.run("do things")

    data = agent.serialize()

    assert data["info"]["carryon"]["fold_stats"]["committed"] == 1
    assert data["info"]["carryon"]["carriers"][0]["subject"] == "src/a.py"
    assert data["info"]["carryon"]["fold_index"] == agent.fold_index
    json.dumps(data)
    assert trajectory_usage(data).folds_committed == 1


def test_sliding_window_agent_truncates():
    m = model(10)
    agent = SlidingWindowAgent(m, LocalEnvironment(), window_messages=4, **AGENT_CONFIG)
    agent.run("do things")
    assert max(len(v) for v in m.seen) <= 2 + 4


def test_limits_checked_before_fold():
    rt = CountingRuntime()
    agent = CarryOnAgent(model(3), LocalEnvironment(), runtime=rt, **{**AGENT_CONFIG, "step_limit": 1})
    info = agent.run("t")
    assert info["exit_status"] == "LimitsExceeded"
    assert rt.fold_calls == 0


def test_split_live_tail_zero_tokens():
    msgs = [{"role": "system"}, {"role": "user"}, {"role": "assistant"}, {"role": "tool"}]
    assert split_live_tail(msgs, fold_index=2, keep_recent_tokens=0) == len(msgs)


def test_split_live_tail_tool_message_advances():
    # Step 0: assistant + tool
    # Step 1: assistant + tool
    msgs = [
        {"role": "system"},
        {"role": "user"},
        {"role": "assistant", "content": "step 0"},
        {"role": "tool", "content": "long output " * 20},
        {"role": "assistant", "content": "step 1"},
        {"role": "tool", "content": "long output " * 20},
    ]
    # With keep_recent_tokens = 70, the shortest suffix with >= 70 tokens
    # starts at index 3 (msgs[3] is tool 0, giving 121 tokens).
    # safe_tail_start moves it forward to index 4 (step 1 assistant).
    kept_start = split_live_tail(msgs, fold_index=2, keep_recent_tokens=70)
    assert kept_start == 4
    assert msgs[kept_start]["role"] == "assistant"


def test_split_live_tail_not_enough_tokens_returns_fold_index():
    msgs = [
        {"role": "system"},
        {"role": "user"},
        {"role": "assistant", "content": "short"},
    ]
    assert split_live_tail(msgs, fold_index=2, keep_recent_tokens=1000) == 2
