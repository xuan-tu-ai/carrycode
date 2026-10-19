"""Fold orchestration: trigger -> Tracker -> Grounder -> Compiler -> validate -> commit.

Implements §3.3 and Appendix A.1 "Update Procedure". In this implementation (as in the
paper), a successful fold covers the entire live tail.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from carrycode.compiler import Compiler
from carrycode.records import ExecutionContext
from carrycode.registry import CandidateRegistry, CarrierStore
from carrycode.tracker import Tracker
from carrycode.view import estimate_tokens, render_checkpoint

logger = logging.getLogger("carrycode.runtime")


@dataclass
class FoldStats:
    attempts: int = 0
    committed: int = 0
    rejected: list[str] = field(default_factory=list)


class CarryOnRuntime:
    def __init__(
        self,
        tracker: Tracker,
        compiler: Compiler,
        trigger_tokens: int = 6000,
        use_code_checks: bool = True,
    ) -> None:
        self.tracker = tracker
        self.compiler = compiler
        self.trigger_tokens = trigger_tokens
        self.use_code_checks = use_code_checks
        """False = ablation: only file_exists / git_diff checks, no test or compile checks."""
        self.store = CarrierStore()
        self.registry = CandidateRegistry()
        self.ec = ExecutionContext()
        self.stats = FoldStats()
        self._tokens_at_last_scan = 0

    def should_fold(self, live_tail: list[dict]) -> bool:
        """Scan when the text added since the last scan exceeds `trigger_tokens`."""
        return estimate_tokens(live_tail) - self._tokens_at_last_scan >= self.trigger_tokens

    def render_checkpoint(self) -> dict | None:
        return render_checkpoint(self.store.current(), self.ec)

    def fold(self, task: str, live_tail: list[dict], log_offset: int, env) -> bool:
        """Try one fold. Returns True only if carriers and EC were committed.

        On any failure the committed view and the live tail stay unchanged.
        """
        self.stats.attempts += 1
        self._tokens_at_last_scan = estimate_tokens(live_tail)
        try:
            raise NotImplementedError("M1/M2: Tracker.scan -> Grounder -> Compiler.compile -> validate -> commit")
        except NotImplementedError as e:
            self.stats.rejected.append(str(e))
            logger.warning("fold skipped: %s", e)
            return False

    def on_fold_committed(self) -> None:
        self._tokens_at_last_scan = 0
