import pytest

from carrycode.records import CarrierEdit, CarrierRecord, CarrierType
from carrycode.registry import CarrierStore, make_carrier_id


def rec(cid: str, version: int, pred: int | None = None, summary: str = "s") -> CarrierRecord:
    return CarrierRecord(
        carrier_id=cid,
        version=version,
        predecessor_version=pred,
        carrier_type=CarrierType.EXTERNAL_OBJECT,
        subject=f"src/{cid}.py",
        summary=summary,
        committed_at_fold=1,
    )


def test_successor_becomes_current_and_history_is_kept():
    store = CarrierStore()
    store.apply([rec("a", 1)])
    store.apply([rec("a", 2, pred=1, summary="updated")])
    assert store.get("a").summary == "updated"
    assert [r.version for r in store.history("a")] == [1, 2]


def test_unaffected_carriers_keep_their_record():
    store = CarrierStore()
    store.apply([rec("a", 1), rec("b", 1)])
    store.apply([rec("a", 2, pred=1)])
    assert store.get("b").version == 1


def test_apply_is_atomic_on_bad_version():
    store = CarrierStore()
    store.apply([rec("a", 1)])
    with pytest.raises(ValueError):
        store.apply([rec("b", 1), rec("a", 3, pred=2)])
    assert store.get("b") is None
    assert store.get("a").version == 1


def test_make_carrier_id_normalizes_paths():
    assert make_carrier_id(CarrierType.EXTERNAL_OBJECT, "/testbed/src/./a.py") == "external_object:src/a.py"
    assert make_carrier_id(CarrierType.EXTERNAL_OBJECT, "./src/a.py") == "external_object:src/a.py"
    assert make_carrier_id(CarrierType.EXTERNAL_OBJECT, " src/a.py ") == "external_object:src/a.py"


def test_make_carrier_id_collapses_whitespace():
    assert (
        make_carrier_id(CarrierType.INFORMATION_PRODUCT, "root  cause\nof bug")
        == "information_product:root cause of bug"
    )


def test_materialize_assigns_versions():
    store = CarrierStore()
    v1_edit = CarrierEdit(
        candidate_id="C1",
        carrier_type=CarrierType.EXTERNAL_OBJECT,
        subject="src/a.py",
        summary="v1",
    )
    store.apply(store.materialize([v1_edit], fold_number=1))

    update_edit = CarrierEdit(
        candidate_id="C1",
        carrier_id="external_object:src/a.py",
        base_version=1,
        carrier_type=CarrierType.EXTERNAL_OBJECT,
        subject="src/a.py",
        summary="v2",
    )
    new_edit = CarrierEdit(
        candidate_id="C1",
        carrier_type=CarrierType.EXTERNAL_OBJECT,
        subject="src/b.py",
        summary="new",
    )
    records = store.materialize([update_edit, new_edit], fold_number=7)

    assert [r.version for r in records] == [2, 1]
    assert [r.predecessor_version for r in records] == [1, None]
    assert all(r.committed_at_fold == 7 for r in records)
    assert store.get("external_object:src/a.py").version == 1
    assert store.get("external_object:src/b.py") is None
