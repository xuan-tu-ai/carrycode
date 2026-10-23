"""Agents: subclasses of mini-swe-agent's DefaultAgent that change only what the model sees.

`self.messages` stays the full, append-only interaction log, so mini-swe-agent's trajectory
saving keeps working. `query()` sends a context view instead.
"""

from __future__ import annotations

import time

from minisweagent.agents.default import AgentConfig, DefaultAgent
from minisweagent.exceptions import LimitsExceeded, TimeExceeded

from carrycode.runtime import CarryOnRuntime
from carrycode.view import build_view, safe_tail_start

HEAD_LEN = 2  # system message + task message


class ViewAgent(DefaultAgent):
    """Base class: same as DefaultAgent.query, but sends `self.build_view()`.

    The limit checks mirror DefaultAgent.query (mini-swe-agent 2.4.6). Re-check them when
    upgrading mini-swe-agent.
    """

    def build_view(self) -> list[dict]:
        return self.messages

    def _check_limits(self) -> None:
        cfg = self.config
        if 0 < cfg.step_limit <= self.n_calls or 0 < cfg.cost_limit <= self.cost:
            raise LimitsExceeded(
                {
                    "role": "exit",
                    "content": "LimitsExceeded",
                    "extra": {"exit_status": "LimitsExceeded", "submission": ""},
                }
            )
        if 0 < cfg.wall_time_limit_seconds <= int(time.time() - self._start_time):
            raise TimeExceeded(
                {"role": "exit", "content": "TimeExceeded", "extra": {"exit_status": "TimeExceeded", "submission": ""}}
            )

    def query(self) -> dict:
        self._check_limits()
        self.n_calls += 1
        message = self.model.query(self.build_view())
        self.cost += message.get("extra", {}).get("cost", 0.0)
        self.add_messages(message)
        return message


class SlidingWindowConfig(AgentConfig):
    window_messages: int = 30


class SlidingWindowAgent(ViewAgent):
    """Baseline from paper Table 4: keep only the most recent messages."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, config_class=SlidingWindowConfig, **kwargs)

    def build_view(self) -> list[dict]:
        start = max(HEAD_LEN, len(self.messages) - self.config.window_messages)
        return self.messages[:HEAD_LEN] + self.messages[safe_tail_start(self.messages, start) :]


class CarryOnAgent(ViewAgent):
    def __init__(self, *args, runtime: CarryOnRuntime, **kwargs):
        super().__init__(*args, **kwargs)
        self.runtime = runtime
        self.fold_index = HEAD_LEN
        """b_k + 1: first log index of the live tail."""

    def build_view(self) -> list[dict]:
        return build_view(self.messages, self.fold_index, self.runtime.render_checkpoint(), head_len=HEAD_LEN)

    def query(self) -> dict:
        self._check_limits()
        tail = self.messages[self.fold_index :]
        if tail and self.runtime.should_fold(tail):
            task = self.extra_template_vars.get("task", "")
            if self.runtime.fold(task, tail, log_offset=self.fold_index, env=self.env):
                self.fold_index = len(self.messages)  # the fold covers the whole live tail
                self.runtime.on_fold_committed()
        return super().query()
