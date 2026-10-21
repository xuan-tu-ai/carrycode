from carrycode.records import CarrierRecord, CarrierType, ExecutionContext
from carrycode.view import (
    build_view,
    estimate_tokens,
    project_tail,
    render_checkpoint,
    safe_tail_start,
    step_texts,
)

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


def test_project_tail_numbers_steps_from_offset():
    result = project_tail(LOG[2:], 2)
    assert result.startswith("[step 2] assistant:")
    assert "[step 3] tool: out1" in result
    assert "[step 5] assistant: next" in result


def test_project_tail_blocks_separated_by_blank_line():
    assert project_tail(LOG[3:5], 3) == "[step 3] tool: out1\n\n[step 4] tool: out2"


def test_project_tail_truncates_long_messages():
    msg = [{"role": "user", "content": "a" * 5000}]
    result = project_tail(msg, 0, max_chars=100)
    assert "...[4900 chars cut]..." in result
    assert len(result) < 200


def test_step_texts_ignores_out_of_range():
    assert step_texts(LOG[2:], 2, [1, 3, 99]) == {3: "out1"}
