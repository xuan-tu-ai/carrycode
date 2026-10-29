"""Compiler: jointly proposes carrier edits and a revised execution context (§3.3, Eq. 2).

(ΔA_t, Ê_{k+1}) = Compile(U_t, E_k, Π(L_t))
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from carrycode.grounder.base import CheckResult
from carrycode.llm import RoleLLM
from carrycode.prompts import load_prompt
from carrycode.records import Candidate, CarrierEdit, CarrierRecord, ExecutionContext


class EvidencePackage(BaseModel):
    """U_t: everything a compilation is allowed to rely on, frozen before the Compiler runs."""

    candidates: list[Candidate]
    prior_records: list[CarrierRecord] = Field(default_factory=list)
    evidence: dict[int, str] = Field(default_factory=dict)
    """Log index -> authorized text of that step."""
    check_results: list[CheckResult] = Field(default_factory=list)


class CompilerOutput(BaseModel):
    carrier_edits: list[CarrierEdit] = Field(default_factory=list)
    execution_context: ExecutionContext
    abstain_reason: str | None = None
    """Set when an honest replacement for the live tail cannot be built."""


def build_compiler_user_message(package: EvidencePackage, ec: ExecutionContext, live_tail_text: str) -> str:
    candidates_text = json.dumps([c.model_dump(mode="json") for c in package.candidates], indent=2)

    if package.prior_records:
        prior_text = json.dumps([r.model_dump(mode="json") for r in package.prior_records], indent=2)
    else:
        prior_text = "none"

    if package.evidence:
        evidence_text = "\n\n".join(f"## step {n}\n{package.evidence[n]}" for n in sorted(package.evidence))
    else:
        evidence_text = "none"

    ec_text = json.dumps(ec.model_dump(mode="json"), indent=2)

    sections = [
        f"# Selected candidates\n{candidates_text}",
        f"# Prior carrier records\n{prior_text}",
        f"# Evidence\n{evidence_text}",
        f"# Current execution context\n{ec_text}",
        f"# Live tail\n{live_tail_text}",
    ]
    return "\n\n".join(sections)


class Compiler:
    def __init__(self, llm: RoleLLM) -> None:
        self.llm = llm

    def compile(self, package: EvidencePackage, ec: ExecutionContext, live_tail_text: str) -> CompilerOutput:
        """Implements §3.3 "Joint Compilation" (Eq. 2)."""
        user = build_compiler_user_message(package, ec, live_tail_text)
        result = self.llm.complete_json(load_prompt("compiler"), user, CompilerOutput)
        if result is None:
            return CompilerOutput(execution_context=ec.model_copy(deep=True), abstain_reason="invalid_output")
        return result
