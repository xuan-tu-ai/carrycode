from __future__ import annotations

from carrycode.prompts import load_prompt
from carrycode.records import Candidate, ExecutionContext, Obligation
from carrycode.testing import ScriptedRoleLLM
from carrycode.tracker import Tracker, TrackerOutput, build_tracker_user_message


def cand(cid: str) -> dict:
    return {
        "candidate_id": cid,
        "provisional_type": "information_product",
        "subject": "bug reproduction",
        "description": "Reproduction test confirms error",
        "supporting_steps": [1, 2],
        "target_carrier_id": None,
        "first_seen_step": 1,
        "last_revised_step": 2,
    }


def test_user_message_sections_in_order():
    msg = build_tracker_user_message(
        task="fix parser",
        live_tail_text="[step 1] tool: out",
        candidates=[],
        carriers=[],
        ec=ExecutionContext(),
        max_requests=4,
    )
    headers = [
        "# Task",
        "# Current carriers",
        "# Candidates",
        "# Open obligations",
        "# Limits",
        "# Live tail",
    ]
    indices = [msg.index(h) for h in headers]
    assert indices == sorted(indices)
    assert "# Current carriers\nnone" in msg
    assert "# Candidates\nnone" in msg
    assert "# Open obligations\nnone" in msg
    assert "Return at most 4 compile_requests." in msg


def test_user_message_lists_open_obligations_only():
    ec = ExecutionContext(
        obligations=[
            Obligation(obligation_id="O1", text="write test", resolved=False),
            Obligation(obligation_id="O2", text="clean up", resolved=True),
        ]
    )
    msg = build_tracker_user_message(
        task="fix parser",
        live_tail_text="[step 1] tool: out",
        candidates=[],
        carriers=[],
        ec=ec,
        max_requests=4,
    )
    assert "- [O1] write test" in msg
    assert "[O2]" not in msg


def test_scan_parses_reply():
    llm = ScriptedRoleLLM(
        [
            {
                "candidate_updates": [cand("C1")],
                "compile_requests": [{"candidate_id": "C1", "evidence_steps": [3]}],
            }
        ]
    )
    tracker = Tracker(llm)
    result = tracker.scan("task", "[step 3] out", [], [], ExecutionContext())

    assert len(result.candidate_updates) == 1
    assert result.candidate_updates[0].candidate_id == "C1"
    assert len(result.compile_requests) == 1
    assert result.compile_requests[0].candidate_id == "C1"
    assert llm.requests[0][0]["content"] == load_prompt("tracker")


def test_scan_caps_requests():
    llm = ScriptedRoleLLM(
        [
            {
                "candidate_updates": [cand("C1"), cand("C2"), cand("C3")],
                "compile_requests": [
                    {"candidate_id": "C1", "evidence_steps": [1]},
                    {"candidate_id": "C2", "evidence_steps": [2]},
                    {"candidate_id": "C3", "evidence_steps": [3]},
                ],
            }
        ]
    )
    tracker = Tracker(llm, max_requests_per_scan=2)
    result = tracker.scan("task", "tail", [], [], ExecutionContext())
    assert len(result.compile_requests) == 2
    assert [r.candidate_id for r in result.compile_requests] == ["C1", "C2"]


def test_scan_drops_requests_for_unknown_candidates():
    llm = ScriptedRoleLLM(
        [
            {
                "candidate_updates": [cand("C1")],
                "compile_requests": [
                    {"candidate_id": "C1", "evidence_steps": [1]},
                    {"candidate_id": "C9", "evidence_steps": [2]},
                ],
            }
        ]
    )
    tracker = Tracker(llm)
    result = tracker.scan("task", "tail", [], [], ExecutionContext())
    assert len(result.compile_requests) == 1
    assert result.compile_requests[0].candidate_id == "C1"


def test_scan_keeps_requests_for_existing_candidates():
    existing_candidate = Candidate(**cand("C1"))
    llm = ScriptedRoleLLM(
        [
            {
                "candidate_updates": [],
                "compile_requests": [{"candidate_id": "C1", "evidence_steps": [1]}],
            }
        ]
    )
    tracker = Tracker(llm)
    result = tracker.scan("task", "tail", [existing_candidate], [], ExecutionContext())
    assert len(result.compile_requests) == 1
    assert result.compile_requests[0].candidate_id == "C1"


def test_scan_filters_resolved_obligations():
    ec = ExecutionContext(
        obligations=[
            Obligation(obligation_id="O1", text="write test", resolved=False),
            Obligation(obligation_id="O2", text="clean up", resolved=True),
        ]
    )
    llm = ScriptedRoleLLM(
        [
            {
                "candidate_updates": [],
                "compile_requests": [],
                "resolved_obligation_ids": ["O1", "O7"],
            }
        ]
    )
    tracker = Tracker(llm)
    result = tracker.scan("task", "tail", [], [], ec)
    assert result.resolved_obligation_ids == ["O1"]


def test_scan_returns_empty_on_invalid_output():
    llm = ScriptedRoleLLM(["bad", "bad"])
    tracker = Tracker(llm)
    result = tracker.scan("task", "tail", [], [], ExecutionContext())
    assert result == TrackerOutput()
