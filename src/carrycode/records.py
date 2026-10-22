"""Data models for the context view.

Implements the records of paper §3.2 and Appendix A.1: candidates, versioned carrier records,
claims for information products, and the execution context.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CarrierType(StrEnum):
    """The three carrier forms of §3.2."""

    EXTERNAL_OBJECT = "external_object"  # an edited file in the repo
    INFORMATION_PRODUCT = "information_product"  # findings stored as claims
    SITUATED_STATE = "situated_state"  # environment state (installed packages, branch, ...)


class Claim(BaseModel):
    """One proposition inside an information product (Appendix A.1)."""

    claim_id: str
    proposition: str
    value: str | None = None
    source_steps: list[int] = Field(default_factory=list)
    """Indices into the interaction log that support this claim."""
    evidence_refs: list[str] = Field(default_factory=list)
    """Coding evidence, e.g. "src/foo.py:42" or "pytest tests/test_x.py::test_y"."""
    retracted: bool = False


class CarrierRecord(BaseModel):
    """A committed carrier version. Updates create a successor with the same `carrier_id`."""

    carrier_id: str
    version: int = 1
    predecessor_version: int | None = None
    carrier_type: CarrierType
    subject: str
    """Stable identity: a normalized file path, or a structured subject for findings/state."""
    summary: str
    """The reusable progress this carrier holds."""
    conditions: list[str] = Field(default_factory=list)
    """Conditions under which the progress can be reused."""
    claims: list[Claim] = Field(default_factory=list)
    """Only for information products."""
    committed_at_fold: int


class CarrierEdit(BaseModel):
    """A carrier change proposed by the Compiler (§3.3 Eq. 2, ΔA_t). The runtime turns it into a CarrierRecord."""

    candidate_id: str
    """The selected candidate this edit compiles."""
    carrier_id: str | None = None
    """None for a new carrier (the id is derived from type + subject); set to update an existing carrier."""
    base_version: int | None = None
    """For updates: the current version this edit was based on. Must be None for new carriers."""
    carrier_type: CarrierType
    subject: str
    summary: str
    conditions: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)


class Candidate(BaseModel):
    """Progress that may become a carrier (Appendix A.1, "Candidate Records")."""

    candidate_id: str
    provisional_type: CarrierType
    subject: str
    description: str
    supporting_steps: list[int] = Field(default_factory=list)
    target_carrier_id: str | None = None
    """Set when the candidate updates an existing carrier."""
    first_seen_step: int
    last_revised_step: int


class Obligation(BaseModel):
    """An open duty the agent still owes (deliverable, unperformed step, ...)."""

    obligation_id: str
    text: str
    source_steps: list[int] = Field(default_factory=list)
    resolved: bool = False


class ExecutionContext(BaseModel):
    """Information needed to continue that carriers do not capture (§3.2)."""

    current_focus: list[str] = Field(default_factory=list)
    active_constraints: list[str] = Field(default_factory=list)
    obligations: list[Obligation] = Field(default_factory=list)
    immediate_continuation: list[str] = Field(default_factory=list)

    def open_obligations(self) -> list[Obligation]:
        return [o for o in self.obligations if not o.resolved]
