from __future__ import annotations

from carrycode.compiler import Compiler, EvidencePackage, build_compiler_user_message
from carrycode.prompts import load_prompt
from carrycode.records import Candidate, CarrierType, ExecutionContext
from carrycode.testing import ScriptedRoleLLM


def test_user_message_sections_in_order():
    cand = Candidate(
        candidate_id="C1",
        provisional_type=CarrierType.EXTERNAL_OBJECT,
        subject="src/a.py",
        description="desc",
        first_seen_step=1,
        last_revised_step=2,
    )
    pkg = EvidencePackage(
        candidates=[cand],
        prior_records=[],
        evidence={5: "x", 3: "y"},
    )
    ec = ExecutionContext()
    msg = build_compiler_user_message(pkg, ec, "live tail text")

    headers = [
        "# Selected candidates",
        "# Prior carrier records",
        "# Evidence",
        "# Current execution context",
        "# Live tail",
    ]
    indices = [msg.index(h) for h in headers]
    assert indices == sorted(indices)

    assert "## step 3\ny" in msg
    assert "## step 5\nx" in msg
    assert msg.index("## step 3\ny") < msg.index("## step 5\nx")
    assert "# Prior carrier records\nnone" in msg


def test_compile_parses_reply():
    reply = {
        "carrier_edits": [
            {
                "candidate_id": "C1",
                "carrier_type": "external_object",
                "subject": "src/a.py",
                "summary": "added fix",
                "conditions": [],
                "claims": [],
            }
        ],
        "execution_context": {
            "current_focus": ["run tests"],
            "active_constraints": [],
            "obligations": [],
            "immediate_continuation": [],
        },
        "abstain_reason": None,
    }
    llm = ScriptedRoleLLM([reply])
    compiler = Compiler(llm)
    pkg = EvidencePackage(candidates=[])
    ec = ExecutionContext()

    out = compiler.compile(pkg, ec, "tail")

    assert len(out.carrier_edits) == 1
    assert out.carrier_edits[0].candidate_id == "C1"
    assert out.execution_context.current_focus == ["run tests"]
    assert llm.requests[0][0]["content"] == load_prompt("compiler")


def test_compile_abstains_on_invalid_output():
    llm = ScriptedRoleLLM(["bad", "bad"])
    compiler = Compiler(llm)
    pkg = EvidencePackage(candidates=[])
    ec = ExecutionContext(current_focus=["working"])

    out = compiler.compile(pkg, ec, "tail")

    assert out.abstain_reason == "invalid_output"
    assert out.carrier_edits == []
    assert out.execution_context == ec
    assert out.execution_context is not ec


def test_compile_passes_through_model_abstain():
    reply = {
        "carrier_edits": [],
        "execution_context": {},
        "abstain_reason": "not ready",
    }
    llm = ScriptedRoleLLM([reply])
    compiler = Compiler(llm)
    pkg = EvidencePackage(candidates=[])
    ec = ExecutionContext()

    out = compiler.compile(pkg, ec, "tail")

    assert out.abstain_reason == "not ready"
    assert out.carrier_edits == []
