"""Validation before commit (§3.3, "Validation and Commitment").

These checks guard the runtime against inconsistent updates. They do not verify task
correctness.
"""

from __future__ import annotations

from carrycode.compiler import CompilerOutput, EvidencePackage
from carrycode.registry import CarrierStore, make_carrier_id


def validate(output: CompilerOutput, package: EvidencePackage, store: CarrierStore) -> list[str]:
    """Return a list of problems; an empty list means the fold may be committed."""
    problems: list[str] = []
    if output.abstain_reason:
        problems.append(f"compiler abstained: {output.abstain_reason}")
    if not output.carrier_edits:
        problems.append("a fold must change at least one carrier")

    selected_candidate_ids = {c.candidate_id for c in package.candidates}
    allowed_steps = set(package.evidence)
    seen_cids: set[str] = set()

    for edit in output.carrier_edits:
        cid = edit.carrier_id or make_carrier_id(edit.carrier_type, edit.subject)

        if edit.candidate_id not in selected_candidate_ids:
            problems.append(f"{cid}: candidate {edit.candidate_id} was not selected")

        if cid in seen_cids:
            problems.append(f"{cid}: edited twice in one fold")
        else:
            seen_cids.add(cid)

        if edit.carrier_id is None:
            if store.get(cid) is not None:
                problems.append(f"{cid}: carrier exists; an update must set carrier_id and base_version")
            if edit.base_version is not None:
                problems.append(f"{cid}: a new carrier must not set base_version")
        else:
            current = store.get(cid)
            if current is None:
                problems.append(f"{cid}: unknown carrier")
            elif make_carrier_id(edit.carrier_type, edit.subject) != cid:
                # Identity is stable across versions (App. A.1): an update may not move the carrier.
                problems.append(f"{cid}: an update must keep the carrier's type and subject")
            elif edit.base_version != current.version:
                problems.append(f"{cid}: stale base_version {edit.base_version} (current v{current.version})")
            elif (
                edit.summary == current.summary
                and edit.conditions == current.conditions
                and edit.claims == current.claims
            ):
                problems.append(f"{cid}: edit does not change the carrier")

        for claim in edit.claims:
            unauthorized = set(claim.source_steps) - allowed_steps
            if unauthorized:
                problems.append(f"{cid}/{claim.claim_id}: cites unauthorized steps {sorted(unauthorized)}")

    # TODO(M2): check that every object-bound CarrierEdit has a SUPPORTED Grounder verdict in
    # package.check_results.
    return problems
