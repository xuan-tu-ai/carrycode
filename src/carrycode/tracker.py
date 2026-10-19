"""Tracker: identifies reusable progress and requests compilation (§3.3, "Tracking Candidates").

TODO(M1): write the prompt in `prompts/tracker.md` and implement `Tracker.scan`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from carrycode.llm import RoleLLM
from carrycode.records import Candidate, ExecutionContext


class CheckSpec(BaseModel):
    """One Grounder check the Tracker asks for, bound to a candidate (Appendix A.2)."""

    check_name: str
    """One of: file_exists, git_diff_nonempty, python_compiles, test_outcome."""
    target: str
    expected: str | None = None


class CompileRequest(BaseModel):
    candidate_id: str
    evidence_steps: list[int] = Field(default_factory=list)
    """Log indices whose content the Compiler may use as evidence."""
    checks: list[CheckSpec] = Field(default_factory=list)


class TrackerOutput(BaseModel):
    candidate_updates: list[Candidate] = Field(default_factory=list)
    compile_requests: list[CompileRequest] = Field(default_factory=list)
    """At most `max_requests_per_scan` (the paper uses 4)."""
    resolved_obligation_ids: list[str] = Field(default_factory=list)


class Tracker:
    def __init__(self, llm: RoleLLM, max_requests_per_scan: int = 4) -> None:
        self.llm = llm
        self.max_requests_per_scan = max_requests_per_scan

    def scan(
        self,
        task: str,
        live_tail_text: str,
        candidates: list[Candidate],
        ec: ExecutionContext,
    ) -> TrackerOutput:
        raise NotImplementedError("M1: build the prompt and call self.llm.complete_json(..., TrackerOutput)")
