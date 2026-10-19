from carrycode.records import CarrierRecord, CarrierType, ExecutionContext
from carrycode.view import build_view, estimate_tokens, render_checkpoint, safe_tail_start

LOG = [
    {"role": "system", "content": "sys"},
    {"role": "user", "content": "task"},
    {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "bash"}}]},
    {"role": "tool", "content": "out1"},
    {"role": "tool", "content": "out2"},
    {"role": "assistant", "content": "next"},
]


def test_tail_never_starts_with_tool_result():
    assert safe_tail_start(LOG, 3) == 5
    assert safe_tail_start(LOG, 2) == 2


def test_no_checkpoint_before_first_fold():
    assert render_checkpoint([], ExecutionContext()) is None
    assert build_view(LOG, 2, None) == LOG


def test_view_is_head_checkpoint_tail():
    carrier = CarrierRecord(
        carrier_id="a",
        carrier_type=CarrierType.EXTERNAL_OBJECT,
        subject="src/a.py",
        summary="fixed the off-by-one in parse()",
        committed_at_fold=1,
    )
    ckpt = render_checkpoint([carrier], ExecutionContext(current_focus=["run tests"]))
    view = build_view(LOG, 5, ckpt)
    assert view[:2] == LOG[:2]
    assert "src/a.py" in view[2]["content"]
    assert view[3:] == LOG[5:]


def test_estimate_tokens_is_chars_over_four():
    assert estimate_tokens([{"role": "user", "content": "x" * 400}]) == 100
