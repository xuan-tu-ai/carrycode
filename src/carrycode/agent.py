"""Agents: subclasses of mini-swe-agent's DefaultAgent that change only what the model sees.

`self.messages` stays the full, append-only interaction log, so mini-swe-agent's trajectory
saving keeps working. `query()` sends a context view instead.
"""

from __future__ import annotations

import time

from minisweagent.agents.default import AgentConfig, DefaultAgent
from minisweagent.agents.interactive import InteractiveAgent, console
from minisweagent.exceptions import LimitsExceeded, TimeExceeded

from carrycode.runtime import CarryOnRuntime
from carrycode.view import build_view, estimate_tokens, safe_tail_start

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


def split_live_tail(messages: list[dict], fold_index: int, keep_recent_tokens: int) -> int:
    """Return the start index in *messages* of the kept suffix.

    The kept suffix is the shortest suffix whose token estimate is >= keep_recent_tokens,
    or the whole tail. It is moved to a valid boundary with safe_tail_start (so it starts
    at a non-tool message, keeping an assistant call and its tool results together).
    """
    if keep_recent_tokens <= 0:
        return len(messages)

    start = fold_index
    for i in range(len(messages), fold_index, -1):
        if estimate_tokens(messages[i:]) >= keep_recent_tokens:
            start = i
            break

    return safe_tail_start(messages, start)


class CarryOnAgent(ViewAgent):
    def __init__(self, *args, runtime: CarryOnRuntime, **kwargs):
        super().__init__(*args, **kwargs)
        self.runtime = runtime
        self.fold_index = HEAD_LEN
        """b_k + 1: first log index of the live tail."""

    def build_view(self) -> list[dict]:
        return build_view(self.messages, self.fold_index, self.runtime.render_checkpoint(), head_len=HEAD_LEN)

    def serialize(self, *extra_dicts) -> dict:
        carryon = {**self.runtime.snapshot(), "fold_index": self.fold_index}
        return super().serialize({"info": {"carryon": carryon}}, *extra_dicts)

    def query(self) -> dict:
        self._check_limits()
        tail = self.messages[self.fold_index :]
        if tail and self.runtime.should_fold(tail):
            kept_start = split_live_tail(self.messages, self.fold_index, self.runtime.keep_recent_tokens)
            covered = self.messages[self.fold_index : kept_start]
            if covered:
                task = self.extra_template_vars.get("task", "")
                if self.runtime.fold(task, covered, log_offset=self.fold_index, env=self.env):
                    self.fold_index = kept_start
                    kept_suffix = self.messages[self.fold_index :]
                    self.runtime.on_fold_committed(baseline_tokens=estimate_tokens(kept_suffix))
        return super().query()


class InteractiveCarryOnAgent(InteractiveAgent, CarryOnAgent):
    """CarryOnAgent with mini-swe-agent's terminal loop (confirm/yolo/human modes), for `carrycode run`.

    MRO: InteractiveAgent.query handles human mode and limit prompts, then calls CarryOnAgent.query,
    which folds before the model call.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._announced_folds = 0

    def build_view(self) -> list[dict]:
        # Called once per model call, right after any fold, so a new fold is announced before the reply.
        committed = self.runtime.stats.committed
        if committed > self._announced_folds:
            self._announced_folds = committed
            console.print(
                f"\n[bold blue]carryon[/bold blue]: fold {committed} committed; "
                f"the live tail now starts at message {self.fold_index}.",
                highlight=False,
            )
        return super().build_view()
