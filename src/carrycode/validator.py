"""Validation before commit (§3.3, "Validation and Commitment").

These checks guard the runtime against inconsistent updates. They do not verify task
correctness.
"""

from __future__ import annotations

from carrycode.compiler import CompilerOutput, EvidencePackage
from carrycode.registry import CarrierStore


def validate(output: CompilerOutput, package: EvidencePackage, store: CarrierStore) -> list[str]:
    """Return a list of problems; an empty list means the fold may be committed."""
    problems: list[str] = []
    if output.abstain_reason:
        problems.append(f"compiler abstained: {output.abstain_reason}")
    if not output.carrier_edits:
        problems.append("a fold must change at least one carrier")

    allowed_steps = set(package.evidence)
    for edit in output.carrier_edits:
        current = store.get(edit.carrier_id)
        expected_version = 1 if current is None else current.version + 1
        if edit.version != expected_version:
            problems.append(f"{edit.carrier_id}: stale or skipped version {edit.version}")
        for claim in edit.claims:
            unauthorized = set(claim.source_steps) - allowed_steps
            if unauthorized:
                problems.append(f"{edit.carrier_id}/{claim.claim_id}: cites unauthorized steps {sorted(unauthorized)}")
    # TODO(M2): check that each edited carrier maps to a selected candidate, and that every
    # object-bound edit has a SUPPORTED Grounder verdict in package.check_results.
    return problems
