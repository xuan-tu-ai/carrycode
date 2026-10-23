from __future__ import annotations

import json

from carrycode.compiler import Compiler, CompilerOutput, EvidencePackage
from carrycode.records import CarrierEdit, CarrierType, ExecutionContext, Obligation
from carrycode.runtime import CarryOnRuntime
from carrycode.testing import ScriptedRoleLLM
from carrycode.tracker import Tracker

TAIL = [
    {
        "role": "assistant",
        "content": "look",
        "tool_calls": [
            {
                "id": "c1",
                "function": {"name": "bash", "arguments": "{}"},
            }
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "c1",
        "content": "out1",
    },
]


def make_tracker_reply(**kw) -> dict:
    data = {
        "candidate_updates": [
            {
                "candidate_id": "C1",
                "provisional_type": "information_product",
                "subject": "root cause",
                "description": "found root cause",
                "supporting_steps": [2, 3],
                "target_carrier_id": None,
                "first_seen_step": 2,
                "last_revised_step": 3,
            }
        ],
        "compile_requests": [{"candidate_id": "C1", "evidence_steps": [3]}],
        "resolved_obligation_ids": [],
    }
    data.update(kw)
    return data


def make_compiler_reply(**kw) -> dict:
    data = {
        "carrier_edits": [
            {
                "candidate_id": "C1",
                "carrier_id": None,
                "base_version": None,
                "carrier_type": "information_product",
                "subject": "root cause",
                "summary": "root cause description",
                "conditions": [],
                "claims": [
                    {
                        "claim_id": "K1",
                        "proposition": "p",
                        "source_steps": [3],
                    }
                ],
            }
        ],
        "execution_context": {
            "current_focus": ["fix parse"],
            "active_constraints": [],
            "obligations": [],
            "immediate_continuation": [],
        },
        "abstain_reason": None,
    }
    data.update(kw)
    return data


class RecordingCompiler(Compiler):
    def __init__(self, llm) -> None:
        super().__init__(llm)
        self.package: EvidencePackage | None = None
        self.ec_received: ExecutionContext | None = None

    def compile(self, package: EvidencePackage, ec: ExecutionContext, live_tail_text: str) -> CompilerOutput:
        self.package = package
        self.ec_received = ec
        return super().compile(package, ec, live_tail_text)


def test_fold_commits_carrier_and_ec():
    tracker_llm = ScriptedRoleLLM([make_tracker_reply()])
    compiler_llm = ScriptedRoleLLM([make_compiler_reply()])
    rt = CarryOnRuntime(Tracker(tracker_llm), Compiler(compiler_llm))

    res = rt.fold("task", TAIL, 2, env=None)

    assert res is True
    rec = rt.store.get("information_product:root cause")
    assert rec is not None
    assert rec.version == 1
    assert rec.committed_at_fold == 1
    assert rt.ec.current_focus == ["fix parse"]
    assert rt.registry.get("C1") is None
    assert rt.stats.committed == 1
    assert rt.events[-1].committed is True
    assert rt.events[-1].carrier_ids == ["information_product:root cause"]


def test_no_compile_request_keeps_candidates():
    tracker_reply = make_tracker_reply(compile_requests=[])
    tracker_llm = ScriptedRoleLLM([tracker_reply])
    compiler_llm = ScriptedRoleLLM([])
    compiler = Compiler(compiler_llm)
    rt = CarryOnRuntime(Tracker(tracker_llm), compiler)

    res = rt.fold("task", TAIL, 2, env=None)

    assert res is False
    assert rt.registry.get("C1") is not None
    assert rt.store.current() == []
    assert rt.ec == ExecutionContext()
    assert rt.events[-1].reason == "no compile request"
    assert compiler.llm.requests == []


def test_validator_problem_changes_nothing():
    tracker_llm = ScriptedRoleLLM([make_tracker_reply()])
    compiler_reply = make_compiler_reply(
        carrier_edits=[
            {
                "candidate_id": "C1",
                "carrier_id": None,
                "base_version": None,
                "carrier_type": "information_product",
                "subject": "root cause",
                "summary": "s",
                "conditions": [],
                "claims": [
                    {
                        "claim_id": "K1",
                        "proposition": "p",
                        "source_steps": [9],
                    }
                ],
            }
        ]
    )
    compiler_llm = ScriptedRoleLLM([compiler_reply])
    rt = CarryOnRuntime(Tracker(tracker_llm), Compiler(compiler_llm))

    res = rt.fold("task", TAIL, 2, env=None)

    assert res is False
    assert rt.store.current() == []
    assert rt.ec == ExecutionContext()
    assert "cites unauthorized steps [9]" in rt.events[-1].reason


def test_exception_is_caught():
    tracker_llm = ScriptedRoleLLM([make_tracker_reply()])
    compiler_llm = ScriptedRoleLLM([])  # raises on empty
    rt = CarryOnRuntime(Tracker(tracker_llm), Compiler(compiler_llm))

    res = rt.fold("task", TAIL, 2, env=None)

    assert res is False
    assert rt.events[-1].reason.startswith("RuntimeError")
    assert rt.store.current() == []
    assert rt.ec == ExecutionContext()


def test_evidence_limited_to_requested_steps():
    tracker_llm = ScriptedRoleLLM([make_tracker_reply()])
    compiler_llm = ScriptedRoleLLM([make_compiler_reply()])
    compiler = RecordingCompiler(compiler_llm)
    rt = CarryOnRuntime(Tracker(tracker_llm), compiler)

    res = rt.fold("task", TAIL, 2, env=None)

    assert res is True
    assert compiler.package is not None
    assert compiler.package.evidence == {3: "out1"}
    assert compiler.package.check_results == []


def test_resolved_obligation_marked_before_compile():
    tracker_reply = make_tracker_reply(resolved_obligation_ids=["O1"])
    tracker_llm = ScriptedRoleLLM([tracker_reply])
    compiler_reply = make_compiler_reply(
        carrier_edits=[
            {
                "candidate_id": "C1",
                "carrier_id": None,
                "base_version": None,
                "carrier_type": "information_product",
                "subject": "root cause",
                "summary": "s",
                "conditions": [],
                "claims": [
                    {
                        "claim_id": "K1",
                        "proposition": "p",
                        "source_steps": [9],
                    }
                ],
            }
        ]
    )
    compiler_llm = ScriptedRoleLLM([compiler_reply])
    compiler = RecordingCompiler(compiler_llm)
    rt = CarryOnRuntime(Tracker(tracker_llm), compiler)
    rt.ec = ExecutionContext(obligations=[Obligation(obligation_id="O1", text="t")])

    res = rt.fold("task", TAIL, 2, env=None)

    assert res is False
    assert compiler.ec_received is not None
    assert compiler.ec_received.obligations[0].resolved is True
    assert rt.ec.obligations[0].resolved is False


def test_update_uses_prior_record():
    tracker_reply = make_tracker_reply(
        candidate_updates=[
            {
                "candidate_id": "C1",
                "provisional_type": "information_product",
                "subject": "root cause",
                "description": "found root cause",
                "supporting_steps": [2, 3],
                "target_carrier_id": "information_product:root cause",
                "first_seen_step": 2,
                "last_revised_step": 3,
            }
        ]
    )
    tracker_llm = ScriptedRoleLLM([tracker_reply])
    compiler_reply = make_compiler_reply(
        carrier_edits=[
            {
                "candidate_id": "C1",
                "carrier_id": "information_product:root cause",
                "base_version": 1,
                "carrier_type": "information_product",
                "subject": "root cause",
                "summary": "new",
                "conditions": [],
                "claims": [
                    {
                        "claim_id": "K1",
                        "proposition": "p",
                        "source_steps": [3],
                    }
                ],
            }
        ]
    )
    compiler_llm = ScriptedRoleLLM([compiler_reply])
    compiler = RecordingCompiler(compiler_llm)
    rt = CarryOnRuntime(Tracker(tracker_llm), compiler)
    rt.store.apply(
        rt.store.materialize(
            [
                CarrierEdit(
                    candidate_id="C0",
                    carrier_type=CarrierType.INFORMATION_PRODUCT,
                    subject="root cause",
                    summary="old",
                )
            ],
            fold_number=1,
        )
    )

    res = rt.fold("task", TAIL, 2, env=None)

    assert res is True
    rec = rt.store.get("information_product:root cause")
    assert rec is not None
    assert rec.version == 2
    assert compiler.package is not None
    assert len(compiler.package.prior_records) == 1
    assert compiler.package.prior_records[0].version == 1


def test_snapshot_keys():
    rt = CarryOnRuntime(Tracker(ScriptedRoleLLM([])), Compiler(ScriptedRoleLLM([])))

    snap = rt.snapshot()

    assert set(snap) == {"fold_stats", "events", "role_usage", "carriers", "execution_context"}
    assert snap["role_usage"]["tracker"]["calls"] == 0
    json.dumps(snap)


def test_snapshot_without_roles():
    snap = CarryOnRuntime(tracker=None, compiler=None).snapshot()

    assert snap["role_usage"]["compiler"]["calls"] == 0
