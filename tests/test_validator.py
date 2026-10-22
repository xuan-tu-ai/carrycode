from __future__ import annotations

from carrycode.compiler import CompilerOutput, EvidencePackage
from carrycode.records import Candidate, CarrierEdit, CarrierType, Claim, ExecutionContext
from carrycode.registry import CarrierStore
from carrycode.validator import validate


def E(**kw) -> CarrierEdit:
    data = {
        "candidate_id": "C1",
        "carrier_type": CarrierType.EXTERNAL_OBJECT,
        "subject": "src/a.py",
        "summary": "s",
        **kw,
    }
    return CarrierEdit(**data)


def make_pkg() -> EvidencePackage:
    return EvidencePackage(
        candidates=[
            Candidate(
                candidate_id="C1",
                provisional_type=CarrierType.EXTERNAL_OBJECT,
                subject="src/a.py",
                description="d",
                first_seen_step=2,
                last_revised_step=3,
            )
        ],
        evidence={3: "out"},
    )


def test_valid_new_carrier_has_no_problems():
    pkg = make_pkg()
    assert (
        validate(
            CompilerOutput(carrier_edits=[E()], execution_context=ExecutionContext()),
            pkg,
            CarrierStore(),
        )
        == []
    )


def test_abstain_and_empty_edits_are_problems():
    pkg = make_pkg()
    problems = validate(
        CompilerOutput(carrier_edits=[], execution_context=ExecutionContext(), abstain_reason="x"),
        pkg,
        CarrierStore(),
    )
    assert any("compiler abstained: x" in p for p in problems)
    assert any("a fold must change at least one carrier" in p for p in problems)


def test_unselected_candidate_rejected():
    pkg = make_pkg()
    problems = validate(
        CompilerOutput(carrier_edits=[E(candidate_id="C9")], execution_context=ExecutionContext()),
        pkg,
        CarrierStore(),
    )
    assert any("candidate C9 was not selected" in p for p in problems)


def test_existing_carrier_without_update_fields_rejected():
    pkg = make_pkg()
    store = CarrierStore()
    store.apply(store.materialize([E()], fold_number=1))
    problems = validate(
        CompilerOutput(carrier_edits=[E()], execution_context=ExecutionContext()),
        pkg,
        store,
    )
    assert any("carrier exists" in p for p in problems)


def test_stale_base_version_rejected():
    pkg = make_pkg()
    store = CarrierStore()
    store.apply(store.materialize([E(summary="v1")], fold_number=1))
    store.apply(
        store.materialize(
            [E(carrier_id="external_object:src/a.py", base_version=1, summary="v2")],
            fold_number=2,
        )
    )
    problems = validate(
        CompilerOutput(
            carrier_edits=[E(carrier_id="external_object:src/a.py", base_version=1, summary="new")],
            execution_context=ExecutionContext(),
        ),
        pkg,
        store,
    )
    assert any("stale base_version 1 (current v2)" in p for p in problems)


def test_noop_update_rejected():
    pkg = make_pkg()
    store = CarrierStore()
    store.apply(store.materialize([E(summary="s")], fold_number=1))
    problems = validate(
        CompilerOutput(
            carrier_edits=[E(carrier_id="external_object:src/a.py", base_version=1)],
            execution_context=ExecutionContext(),
        ),
        pkg,
        store,
    )
    assert any("edit does not change the carrier" in p for p in problems)


def test_duplicate_edit_rejected():
    pkg = make_pkg()
    problems = validate(
        CompilerOutput(carrier_edits=[E(), E()], execution_context=ExecutionContext()),
        pkg,
        CarrierStore(),
    )
    assert any("edited twice in one fold" in p for p in problems)


def test_unauthorized_claim_steps_rejected():
    pkg = make_pkg()
    edit = E(
        carrier_type=CarrierType.INFORMATION_PRODUCT,
        subject="x",
        claims=[Claim(claim_id="K1", proposition="p", source_steps=[3, 9])],
    )
    problems = validate(
        CompilerOutput(carrier_edits=[edit], execution_context=ExecutionContext()),
        pkg,
        CarrierStore(),
    )
    assert any("cites unauthorized steps [9]" in p for p in problems)


def test_compiler_output_uses_carrier_edit():
    schema = CompilerOutput.model_json_schema()
    assert "candidate_id" in schema["$defs"]["CarrierEdit"]["properties"]
