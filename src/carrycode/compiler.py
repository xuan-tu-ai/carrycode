"""Compiler: jointly proposes carrier edits and a revised execution context (§3.3, Eq. 2).

(ΔA_t, Ê_{k+1}) = Compile(U_t, E_k, Π(L_t))

TODO(M1): write the prompt in `prompts/compiler.md` and implement `Compiler.compile`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from carrycode.grounder.base import CheckResult
from carrycode.llm import RoleLLM
from carrycode.records import Candidate, CarrierRecord, ExecutionContext


class EvidencePackage(BaseModel):
    """U_t: everything a compilation is allowed to rely on, frozen before the Compiler runs."""

    candidates: list[Candidate]
    prior_records: list[CarrierRecord] = Field(default_factory=list)
    evidence: dict[int, str] = Field(default_factory=dict)
    """Log index -> authorized text of that step."""
    check_results: list[CheckResult] = Field(default_factory=list)


class CompilerOutput(BaseModel):
    carrier_edits: list[CarrierRecord] = Field(default_factory=list)
    execution_context: ExecutionContext
    abstain_reason: str | None = None
    """Set when an honest replacement for the live tail cannot be built."""


class Compiler:
    def __init__(self, llm: RoleLLM) -> None:
        self.llm = llm

    def compile(self, package: EvidencePackage, ec: ExecutionContext, live_tail_text: str) -> CompilerOutput:
        raise NotImplementedError("M1: build the prompt and call self.llm.complete_json(..., CompilerOutput)")
