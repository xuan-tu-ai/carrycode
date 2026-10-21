"""Tests for per-trajectory usage metrics."""

from __future__ import annotations

import pytest

from carrycode.metrics import TaskUsage, trajectory_usage


def _make_assistant(prompt_tokens: int, completion_tokens: int) -> dict:
    return {
        "role": "assistant",
        "content": "ok",
        "extra": {
            "response": {
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
            }
        },
    }


def test_host_tokens_summed() -> None:
    traj = {
        "messages": [
            _make_assistant(100, 10),
            {"role": "tool", "content": "output"},
            _make_assistant(200, 20),
        ],
        "info": {"model_stats": {"instance_cost": 0.5, "api_calls": 2}},
    }
    usage = trajectory_usage(traj)
    assert usage.host_input_tokens == 300
    assert usage.host_output_tokens == 30
    assert usage.host_calls == 2
    assert usage.host_cost == 0.5


def test_missing_usage_is_zero() -> None:
    traj = {
        "messages": [{"role": "assistant", "content": "hi"}],
        "info": {"model_stats": {"instance_cost": 0.0, "api_calls": 1}},
    }
    usage = trajectory_usage(traj)
    assert usage.host_input_tokens == 0
    assert usage.host_output_tokens == 0


def test_runtime_section_counted() -> None:
    traj = {
        "messages": [],
        "info": {
            "model_stats": {"instance_cost": 0.0, "api_calls": 0},
            "carryon": {
                "fold_stats": {"attempts": 3, "committed": 1, "rejected": []},
                "role_usage": {
                    "tracker": {"calls": 1, "input_tokens": 50, "output_tokens": 5, "cost": 0.01, "failures": []},
                    "compiler": {"calls": 1, "input_tokens": 70, "output_tokens": 7, "cost": 0.02, "failures": []},
                },
            },
        },
    }
    usage = trajectory_usage(traj)
    assert usage.runtime_calls == 2
    assert usage.runtime_input_tokens == 120
    assert usage.runtime_output_tokens == 12
    assert usage.runtime_cost == pytest.approx(0.03)
    assert usage.folds_attempted == 3
    assert usage.folds_committed == 1


def test_totals() -> None:
    usage = TaskUsage(
        host_input_tokens=100,
        host_output_tokens=10,
        host_cost=0.5,
        runtime_input_tokens=50,
        runtime_output_tokens=5,
        runtime_cost=0.1,
    )
    assert usage.total_tokens() == 165
    assert usage.total_cost() == pytest.approx(0.6)


def test_empty_traj() -> None:
    assert trajectory_usage({}) == TaskUsage()


def test_null_fields_do_not_raise() -> None:
    traj = {
        "messages": [
            {"role": "assistant", "extra": {"response": {"usage": None}}},
            {"role": "assistant", "extra": None},
        ],
        "info": {"exit_status": None, "carryon": {"role_usage": {"tracker": None}, "fold_stats": None}},
    }
    usage = trajectory_usage(traj)
    assert usage.host_input_tokens == 0
    assert usage.exit_status == ""


def test_format_error_response_is_counted() -> None:
    # mini-swe-agent stores the billed response of an unparsable reply on a user-role message.
    traj = {"messages": [_make_assistant(100, 10), {**_make_assistant(40, 4), "role": "user"}]}
    usage = trajectory_usage(traj)
    assert usage.host_input_tokens == 140
    assert usage.host_output_tokens == 14
