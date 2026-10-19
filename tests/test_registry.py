import pytest

from carrycode.records import CarrierRecord, CarrierType
from carrycode.registry import CarrierStore


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
