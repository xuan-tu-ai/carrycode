"""Fold orchestration: trigger -> Tracker -> Grounder -> Compiler -> validate -> commit.

Implements §3.3 and Appendix A.1 "Update Procedure". In M1, the Grounder is skipped (moved to M2).
In this implementation (as in the paper), a successful fold covers the entire live tail.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from carrycode.compiler import Compiler, EvidencePackage
from carrycode.records import ExecutionContext
from carrycode.registry import CandidateRegistry, CarrierStore
from carrycode.tracker import Tracker
from carrycode.validator import validate
from carrycode.view import estimate_tokens, project_tail, render_checkpoint, step_texts

logger = logging.getLogger("carrycode.runtime")


class FoldEvent(BaseModel):
    """One fold attempt, kept for analysis (paper §4.5 carrier persistence)."""

    attempt: int
    log_offset: int
    tail_messages: int
    tail_tokens: int
    committed: bool
    reason: str = ""
    """Why the fold was rejected; empty when committed."""
    carrier_ids: list[str] = Field(default_factory=list)
    """Carriers written by this fold."""


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
        self.events: list[FoldEvent] = []

    def _reject(self, base: dict, reason: str) -> bool:
        self.stats.rejected.append(reason)
        self.events.append(FoldEvent(**base, committed=False, reason=reason))
        logger.info("fold rejected: %s", reason)
        return False

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
        base = {
            "attempt": self.stats.attempts,
            "log_offset": log_offset,
            "tail_messages": len(live_tail),
            "tail_tokens": self._tokens_at_last_scan,
        }
        try:
            tail_text = project_tail(live_tail, log_offset)
            scan = self.tracker.scan(task, tail_text, self.registry.all(), self.store.current(), self.ec)
            for candidate in scan.candidate_updates:
                self.registry.upsert(candidate)  # kept even if this fold fails (App. A.1)
            if not scan.compile_requests:
                return self._reject(base, "no compile request")
            candidates = [c for r in scan.compile_requests if (c := self.registry.get(r.candidate_id)) is not None]
            steps = sorted({s for r in scan.compile_requests for s in r.evidence_steps})
            prior = [
                p for c in candidates if c.target_carrier_id and (p := self.store.get(c.target_carrier_id)) is not None
            ]
            package = EvidencePackage(
                candidates=candidates,
                prior_records=prior,
                evidence=step_texts(live_tail, log_offset, steps),
                check_results=[],
            )
            ec_in = self.ec.model_copy(deep=True)
            for obligation in ec_in.obligations:
                if obligation.obligation_id in scan.resolved_obligation_ids:
                    obligation.resolved = True
            output = self.compiler.compile(package, ec_in, tail_text)
            problems = validate(output, package, self.store)
            if problems:
                return self._reject(base, "; ".join(problems))
            records = self.store.materialize(output.carrier_edits, fold_number=self.stats.committed + 1)
            self.store.apply(records)  # atomic; raises ValueError on a bad version chain
        except Exception as e:  # a fold must never crash the agent
            logger.exception("fold failed")
            return self._reject(base, f"{type(e).__name__}: {e}")
        self.ec = output.execution_context
        for candidate in candidates:
            self.registry.remove(candidate.candidate_id)
        self.stats.committed += 1
        self.events.append(FoldEvent(**base, committed=True, carrier_ids=[r.carrier_id for r in records]))
        return True

    def on_fold_committed(self) -> None:
        self._tokens_at_last_scan = 0
