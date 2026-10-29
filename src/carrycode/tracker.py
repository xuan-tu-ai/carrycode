"""Tracker: identifies reusable progress and requests compilation (§3.3, "Tracking Candidates")."""

import json

from pydantic import BaseModel, Field

from carrycode.llm import RoleLLM
from carrycode.prompts import load_prompt
from carrycode.records import Candidate, CarrierRecord, ExecutionContext


class CheckSpec(BaseModel):
    """One Grounder check the Tracker asks for, bound to a candidate (Appendix A.2)."""

    check_name: str
    """One of: file_exists, git_diff_nonempty, python_compiles, test_outcome, command_exit."""
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


def build_tracker_user_message(
    task: str,
    live_tail_text: str,
    candidates: list[Candidate],
    carriers: list[CarrierRecord],
    ec: ExecutionContext,
    max_requests: int,
) -> str:
    if carriers:
        carriers_text = json.dumps(
            [
                c.model_dump(
                    mode="json",
                    include={"carrier_id", "version", "carrier_type", "subject", "summary"},
                )
                for c in carriers
            ],
            indent=2,
        )
    else:
        carriers_text = "none"

    if candidates:
        candidates_text = json.dumps([c.model_dump(mode="json") for c in candidates], indent=2)
    else:
        candidates_text = "none"

    open_obligations = ec.open_obligations()
    if open_obligations:
        obligations_text = "\n".join(f"- [{o.obligation_id}] {o.text}" for o in open_obligations)
    else:
        obligations_text = "none"

    sections = [
        f"# Task\n{task}",
        f"# Current carriers\n{carriers_text}",
        f"# Candidates\n{candidates_text}",
        f"# Open obligations\n{obligations_text}",
        f"# Limits\nReturn at most {max_requests} compile_requests.",
        f"# Live tail\n{live_tail_text}",
    ]
    return "\n\n".join(sections)


class Tracker:
    def __init__(self, llm: RoleLLM, max_requests_per_scan: int = 4) -> None:
        self.llm = llm
        self.max_requests_per_scan = max_requests_per_scan

    def scan(
        self,
        task: str,
        live_tail_text: str,
        candidates: list[Candidate],
        carriers: list[CarrierRecord],
        ec: ExecutionContext,
    ) -> TrackerOutput:
        """Implements §3.3 "Tracking Candidates": propose candidate updates and compile requests."""
        user = build_tracker_user_message(task, live_tail_text, candidates, carriers, ec, self.max_requests_per_scan)
        result = self.llm.complete_json(load_prompt("tracker"), user, TrackerOutput)
        if result is None:
            return TrackerOutput()
        known = {c.candidate_id for c in candidates} | {c.candidate_id for c in result.candidate_updates}
        requests = [r for r in result.compile_requests if r.candidate_id in known][: self.max_requests_per_scan]
        open_ids = {o.obligation_id for o in ec.open_obligations()}
        resolved = [i for i in result.resolved_obligation_ids if i in open_ids]
        return TrackerOutput(
            candidate_updates=result.candidate_updates,
            compile_requests=requests,
            resolved_obligation_ids=resolved,
        )
