"""Export parity fixtures for dsh-carryon, the TypeScript port of the CarryOn runtime.

Each case holds an input and the output carrycode produces for it. dsh-carryon vendors these files and its
test suite must reproduce every expected value (design doc `docs/design/dsh-plugin.md` §6, "Parity fixtures").
`tests/test_parity_fixtures.py` fails when the committed files differ from what this script generates.

Usage:
    uv run python scripts/export_parity_fixtures.py           # write tests/fixtures/parity/*.json
    uv run python scripts/export_parity_fixtures.py --check   # exit 1 if the committed files are out of date

Fixture format (version 1): {"format": 1, "module": ..., "cases": [{"op", "name", "input", "expected"}]}.
Messages use the shape both runtimes share: `content` is a string or a list of `{"type": "text", "text": ...}`
parts. Tool calls are not covered: carrycode renders OpenAI `tool_calls`, dsh has `tool-call` content blocks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from carrycode.compiler import Compiler, CompilerOutput, EvidencePackage, build_compiler_user_message
from carrycode.llm import strip_code_fence
from carrycode.records import Candidate, CarrierEdit, CarrierRecord, CarrierType, ExecutionContext
from carrycode.registry import CarrierStore, make_carrier_id
from carrycode.testing import ScriptedRoleLLM
from carrycode.tracker import Tracker, build_tracker_user_message
from carrycode.validator import validate
from carrycode.view import estimate_tokens, message_text, project_tail, render_checkpoint, step_texts

FORMAT = 1
OUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "parity"

EO = CarrierType.EXTERNAL_OBJECT.value
IP = CarrierType.INFORMATION_PRODUCT.value
SS = CarrierType.SITUATED_STATE.value


def case(op: str, name: str, input: dict[str, Any], expected: Any) -> dict[str, Any]:
    return {"op": op, "name": name, "input": input, "expected": expected}


def dump(records: list[CarrierRecord]) -> list[dict[str, Any]]:
    return [r.model_dump(mode="json") for r in records]


def store_from(records: list[dict[str, Any]]) -> CarrierStore:
    """A store holding `records`, committed one by one in list order."""
    store = CarrierStore()
    for r in records:
        store.apply([CarrierRecord.model_validate(r)])
    return store


def record(carrier_type: str, subject: str, version: int = 1, fold: int = 1, **kw: Any) -> dict[str, Any]:
    """A committed record (JSON form) whose id is derived from type and subject."""
    ct = CarrierType(carrier_type)
    return CarrierRecord(
        carrier_id=make_carrier_id(ct, subject),
        version=version,
        predecessor_version=None if version == 1 else version - 1,
        carrier_type=ct,
        subject=subject,
        summary=kw.pop("summary", "s"),
        committed_at_fold=fold,
        **kw,
    ).model_dump(mode="json")


def history(cid_type: str, subject: str, versions: int, **kw: Any) -> list[dict[str, Any]]:
    return [record(cid_type, subject, version=v, fold=v, summary=f"s{v}", **kw) for v in range(1, versions + 1)]


# --- registry ---------------------------------------------------------------------------------------------------


def registry_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    ids = [
        ("external plain path", EO, "src/a.py"),
        ("external /testbed/ prefix and whitespace", EO, "  /testbed/src/a.py \n"),
        ("external ./ prefix, double slash and ..", EO, "./src//b/../a.py"),
        ("external trailing slash and .", EO, "a/./b/"),
        ("external absolute path", EO, "/abs/x/../path.py"),
        ("external leading double slash is kept", EO, "//net/share"),
        ("external triple slash collapses", EO, "///x/y"),
        ("external leading .. is kept", EO, "../up/x.py"),
        (".. above an absolute root is dropped", EO, "/../a"),
        ("external empty subject", EO, "   "),
        ("external only /testbed/", EO, "/testbed/"),
        ("information product collapses whitespace", IP, "  Root   cause\n of\tbug "),
        ("situated state collapses whitespace", SS, "branch\t main"),
    ]
    for name, carrier_type, subject in ids:
        cases.append(
            case(
                "make_carrier_id",
                name,
                {"carrier_type": carrier_type, "subject": subject},
                make_carrier_id(CarrierType(carrier_type), subject),
            )
        )

    def materialize_case(name: str, store: list[dict[str, Any]], edits: list[dict[str, Any]], fold: int) -> None:
        parsed = [CarrierEdit.model_validate(e) for e in edits]
        out = store_from(store).materialize(parsed, fold_number=fold)
        cases.append(case("materialize", name, {"store": store, "edits": edits, "fold_number": fold}, dump(out)))

    claim = {"claim_id": "k1", "proposition": "p", "value": "v", "source_steps": [3], "evidence_refs": ["a.py:1"]}
    materialize_case(
        "new carriers start at version 1",
        [],
        [
            {"candidate_id": "C1", "carrier_type": EO, "subject": "./src/a.py", "summary": "edited a"},
            {
                "candidate_id": "C2",
                "carrier_type": IP,
                "subject": "cause",
                "summary": "found",
                "conditions": ["while x"],
                "claims": [claim],
            },
        ],
        1,
    )
    materialize_case(
        "update names the current version as predecessor",
        history(EO, "src/a.py", 2),
        [
            {
                "candidate_id": "C1",
                "carrier_id": "external_object:src/a.py",
                "base_version": 2,
                "carrier_type": EO,
                "subject": "src/a.py",
                "summary": "s3",
            }
        ],
        3,
    )
    materialize_case(
        "an edit without carrier_id for an existing subject still becomes a successor",
        history(SS, "branch", 1),
        [{"candidate_id": "C1", "carrier_type": SS, "subject": "  branch ", "summary": "on main"}],
        2,
    )
    materialize_case(
        "explicit carrier_id of an unknown carrier starts at version 1",
        [],
        [{"candidate_id": "C1", "carrier_id": "custom:id", "carrier_type": IP, "subject": "x", "summary": "s"}],
        4,
    )

    def apply_case(name: str, store: list[dict[str, Any]], records: list[dict[str, Any]]) -> None:
        s = store_from(store)
        expected: dict[str, Any] = {}
        try:
            s.apply([CarrierRecord.model_validate(r) for r in records])
        except ValueError as e:
            expected["error"] = str(e)
        expected["current"] = dump(s.current())
        expected["histories"] = {cid: dump(s.history(cid)) for cid in sorted({r["carrier_id"] for r in records})}
        cases.append(case("apply", name, {"store": store, "records": records}, expected))

    a1, a2, a3 = history(EO, "src/a.py", 3)
    b1 = record(IP, "cause")
    apply_case("new carrier at version 1", [], [a1])
    apply_case("successor of the current version", [a1], [a2])
    apply_case("two carriers in one commit", [a1, a2], [a3, b1])
    apply_case("new carrier must start at version 1", [], [a2])
    apply_case("new carrier must not name a predecessor", [], [{**a1, "predecessor_version": 0}])
    apply_case("skipping a version is rejected", [a1], [a3])
    apply_case("wrong predecessor is rejected", [a1], [{**a2, "predecessor_version": 0}])
    apply_case("a failed commit writes nothing", [a1], [b1, a3])
    apply_case("current keeps first-commit order", [b1, a1], [a2])
    return cases


# --- validator --------------------------------------------------------------------------------------------------


def validator_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    cand = {
        "candidate_id": "C1",
        "provisional_type": EO,
        "subject": "src/a.py",
        "description": "d",
        "first_seen_step": 2,
        "last_revised_step": 3,
    }
    cand2 = {**cand, "candidate_id": "C2", "provisional_type": IP, "subject": "cause"}
    package = {"candidates": [cand, cand2], "evidence": {"3": "out", "5": "more"}}

    def edit(**kw: Any) -> dict[str, Any]:
        return {"candidate_id": "C1", "carrier_type": EO, "subject": "src/a.py", "summary": "s", **kw}

    def output(*edits: dict[str, Any], **kw: Any) -> dict[str, Any]:
        return {"carrier_edits": list(edits), "execution_context": {}, **kw}

    def validate_case(
        name: str, out: dict[str, Any], store: list[dict[str, Any]] | None = None, pkg: dict[str, Any] | None = None
    ) -> None:
        store = store or []
        pkg = pkg or package
        problems = validate(CompilerOutput.model_validate(out), EvidencePackage.model_validate(pkg), store_from(store))
        cases.append(case("validate", name, {"output": out, "package": pkg, "store": store}, problems))

    a1 = record(EO, "src/a.py", summary="s", conditions=["c"])
    claim = {"claim_id": "k1", "proposition": "p", "source_steps": [3]}

    validate_case("valid new carrier", output(edit()))
    validate_case("valid update", output(edit(carrier_id=a1["carrier_id"], base_version=1, summary="s2")), [a1])
    validate_case("abstain and no edits", output(abstain_reason="not enough evidence"))
    validate_case("candidate not selected", output(edit(candidate_id="C9")))
    validate_case("existing carrier without update fields", output(edit()), [a1])
    validate_case("new carrier with base_version", output(edit(base_version=1)))
    validate_case("existing carrier without carrier_id, with base_version", output(edit(base_version=1)), [a1])
    validate_case("update of an unknown carrier", output(edit(carrier_id="external_object:src/zzz.py", base_version=1)))
    validate_case(
        "update may not change the subject",
        output(edit(carrier_id=a1["carrier_id"], base_version=1, subject="src/b.py", summary="s2")),
        [a1],
    )
    validate_case(
        "update may not change the type",
        output(edit(carrier_id=a1["carrier_id"], base_version=1, carrier_type=SS, summary="s2")),
        [a1],
    )
    validate_case(
        "update with an equivalent subject is fine",
        output(edit(carrier_id=a1["carrier_id"], base_version=1, subject="./src//a.py", summary="s2")),
        [a1],
    )
    validate_case("stale base_version", output(edit(carrier_id=a1["carrier_id"], base_version=3, summary="x")), [a1])
    validate_case("missing base_version on update", output(edit(carrier_id=a1["carrier_id"], summary="x")), [a1])
    validate_case(
        "edit that changes nothing",
        output(edit(carrier_id=a1["carrier_id"], base_version=1, conditions=["c"])),
        [a1],
    )
    validate_case(
        "changing only the conditions is a change",
        output(edit(carrier_id=a1["carrier_id"], base_version=1, conditions=["c", "d"])),
        [a1],
    )
    validate_case("same carrier edited twice", output(edit(), edit(subject="./src/a.py", summary="t")))
    validate_case(
        "claims citing unauthorized steps",
        output(
            edit(
                candidate_id="C2",
                carrier_type=IP,
                subject="cause",
                claims=[claim, {**claim, "claim_id": "k2", "source_steps": [9, 2, 3, 9]}],
            )
        ),
    )
    validate_case(
        "several problems keep their order",
        output(
            edit(candidate_id="C7", base_version=2, claims=[{**claim, "source_steps": [4]}]),
            edit(candidate_id="C7", base_version=2),
            abstain_reason="x",
        ),
        [a1],
    )
    validate_case("empty evidence authorizes no steps", output(edit(claims=[claim])), pkg={"candidates": [cand]})
    return cases


# --- view -------------------------------------------------------------------------------------------------------


def view_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    messages = [
        {"role": "system", "content": "You are a coding agent."},
        {"role": "user", "content": [{"type": "text", "text": "Fix the bug"}, {"type": "text", "text": "in a.py"}]},
        {"role": "assistant", "content": "  I will look.  "},
        {"role": "tool", "content": [{"type": "image"}, {"type": "text", "text": "file listing"}]},
        {"role": "assistant", "content": None},
        {"role": "user", "content": "naïve ünïcode 🙂 text"},
        {"content": "no role"},
    ]

    text_messages = [
        ("string content", {"role": "user", "content": "hello"}),
        ("whitespace is stripped", {"role": "assistant", "content": "  \n hello \t"}),
        ("text parts joined by a space", messages[1]),
        ("parts without text leave an empty slot", messages[3]),
        ("non-object parts are skipped", {"role": "user", "content": ["raw", {"type": "text", "text": "x"}]}),
        ("null content", messages[4]),
        ("missing content", {"role": "assistant"}),
        ("empty list", {"role": "user", "content": []}),
    ]
    for name, m in text_messages:
        cases.append(case("message_text", name, {"message": m}, message_text(m)))

    for name, ms in [("all messages", messages), ("no messages", []), ("emoji count as one character", messages[5:6])]:
        cases.append(case("estimate_tokens", name, {"messages": ms}, estimate_tokens(ms)))

    long_text = {"role": "tool", "content": "0123456789abcdefghij🙂klmnopqrstuvwxyz"}
    for name, ms, offset, max_chars in [
        ("short messages, default limit", messages, 4, 2000),
        ("truncated with an even limit", [long_text], 10, 10),
        ("truncated with an odd limit", [long_text], 0, 11),
        ("limit of 1 keeps nothing around the marker", [long_text], 0, 1),
        ("limit of 0", [long_text], 0, 0),
        ("text exactly at the limit is kept", [{"role": "user", "content": "abcd"}], 7, 4),
        ("no messages", [], 0, 2000),
    ]:
        cases.append(
            case(
                "project_tail",
                name,
                {"messages": ms, "offset": offset, "max_chars": max_chars},
                project_tail(ms, offset, max_chars),
            )
        )

    for name, steps in [
        ("steps inside and outside the tail", [11, 9, 16, 10, 17, 13]),
        ("duplicates keep the first position", [12, 11, 12]),
        ("no steps", []),
    ]:
        result = step_texts(messages, 10, steps)
        cases.append(
            case(
                "step_texts",
                name,
                {"messages": messages, "offset": 10, "steps": steps},
                [[s, t] for s, t in result.items()],
            )
        )

    carriers = [
        record(EO, "src/a.py", version=2, summary="patched the parser", conditions=["tests pass on py3.11"]),
        record(
            IP,
            "root cause",
            summary="off-by-one in tokenizer",
            claims=[
                {"claim_id": "k1", "proposition": "loop stops one early", "source_steps": [4]},
                {"claim_id": "k2", "proposition": "retracted idea", "retracted": True},
            ],
        ),
        record(SS, "env", summary="deps installed"),
    ]
    full_ec = {
        "current_focus": ["fix tokenizer"],
        "active_constraints": ["do not edit tests"],
        "obligations": [
            {"obligation_id": "o1", "text": "run the full suite"},
            {"obligation_id": "o2", "text": "done already", "resolved": True},
        ],
        "immediate_continuation": ["rerun pytest", "then commit"],
    }
    for name, cs, ec in [
        ("nothing to show before the first fold", [], {}),
        ("continuation only is still nothing to show", [], {"immediate_continuation": ["next"]}),
        ("execution context only", [], {"current_focus": ["read the code"]}),
        ("resolved obligations alone still render", [], {"obligations": [full_ec["obligations"][1]]}),
        ("carriers only", carriers, {}),
        ("carriers and full execution context", carriers, full_ec),
    ]:
        rendered = render_checkpoint([CarrierRecord.model_validate(c) for c in cs], ExecutionContext.model_validate(ec))
        cases.append(
            case("render_checkpoint", name, {"carriers": cs, "ec": ec}, rendered["content"] if rendered else None)
        )
    return cases


# --- roles ------------------------------------------------------------------------------------------------------


def roles_cases() -> list[dict[str, Any]]:
    """Runtime-role I/O: user messages, JSON reply parsing with one retry, and the Tracker's output filtering."""
    cases: list[dict[str, Any]] = []

    for name, text in [
        ("json fence", '```json\n{"a": 1}\n```'),
        ("bare fence", '```\n{"a": 1}\n```'),
        ("fence with surrounding whitespace and no newline before the close", '  ```json\n{"a": 1}```  \n'),
        ("no fence", '{"a": 1}'),
        ("text after the fence is not stripped", '```json\n{"a": 1}\n```\nThanks!'),
        ("multi-line body", '```JSON\n{\n  "a": [1,\n 2]\n}\n```'),
    ]:
        cases.append(case("strip_code_fence", name, {"text": text}, strip_code_fence(text)))

    cand = {
        "candidate_id": "C1",
        "provisional_type": EO,
        "subject": "src/parser.py",
        "description": "fix the off-by-one – naïve loop",
        "supporting_steps": [12, 14],
        "first_seen_step": 12,
        "last_revised_step": 14,
    }
    cand2 = {**cand, "candidate_id": "C2", "provisional_type": IP, "subject": "root cause", "target_carrier_id": None}
    carrier = record(IP, "root cause", summary="loop stops early 🙂", conditions=["py3.11"])
    ec = {
        "current_focus": ["fix parser"],
        "active_constraints": ["no test edits"],
        "obligations": [
            {"obligation_id": "o1", "text": "run the suite"},
            {"obligation_id": "o2", "text": "already done", "resolved": True},
        ],
        "immediate_continuation": ["rerun pytest"],
    }
    tail = "[step 12] assistant: look\n\n[step 13] tool: out"

    def tracker_message_case(name: str, candidates: list, carriers: list, ec_in: dict, max_requests: int) -> None:
        text = build_tracker_user_message(
            "Fix the parser — résumé task",
            tail,
            [Candidate.model_validate(c) for c in candidates],
            [CarrierRecord.model_validate(c) for c in carriers],
            ExecutionContext.model_validate(ec_in),
            max_requests,
        )
        cases.append(
            case(
                "tracker_user_message",
                name,
                {
                    "task": "Fix the parser — résumé task",
                    "live_tail_text": tail,
                    "candidates": candidates,
                    "carriers": carriers,
                    "ec": ec_in,
                    "max_requests": max_requests,
                },
                text,
            )
        )

    tracker_message_case("empty registry, store and context", [], [], {}, 4)
    tracker_message_case("full inputs, non-ASCII escaped", [cand, cand2], [carrier], ec, 2)

    package = {
        "candidates": [cand],
        "prior_records": [carrier],
        "evidence": {"10": "ten", "9": "nine 🙂", "12": "twelve"},
    }
    for name, pkg in [
        ("evidence sorted by step number", package),
        ("no prior records, no evidence", {"candidates": [cand]}),
    ]:
        text = build_compiler_user_message(
            EvidencePackage.model_validate(pkg), ExecutionContext.model_validate(ec), tail
        )
        cases.append(case("compiler_user_message", name, {"package": pkg, "ec": ec, "live_tail_text": tail}, text))

    good_scan = {
        "candidate_updates": [cand2],
        "compile_requests": [
            {"candidate_id": "C1", "evidence_steps": [12, 13]},
            {"candidate_id": "C9", "evidence_steps": [1]},
            {"candidate_id": "C2", "evidence_steps": [13], "checks": [{"check_name": "file_exists", "target": "a"}]},
            {"candidate_id": "C1", "evidence_steps": [14]},
        ],
        "resolved_obligation_ids": ["o1", "o2", "o9"],
        "ignored_key": True,
    }

    def scan_case(name: str, replies: list[str], max_requests: int = 2) -> None:
        llm = ScriptedRoleLLM(list(replies))
        out = Tracker(llm, max_requests_per_scan=max_requests).scan(
            "task",
            tail,
            [Candidate.model_validate(cand)],
            [CarrierRecord.model_validate(carrier)],
            ExecutionContext.model_validate(ec),
        )
        cases.append(
            case(
                "tracker_scan",
                name,
                {
                    "task": "task",
                    "live_tail_text": tail,
                    "candidates": [cand],
                    "carriers": [carrier],
                    "ec": ec,
                    "max_requests": max_requests,
                    "replies": replies,
                },
                {"output": out.model_dump(mode="json"), "calls": llm.usage.calls},
            )
        )

    scan_case("filters unknown candidates, caps requests, keeps open obligations", [json.dumps(good_scan)])
    scan_case("fenced reply is parsed", ["```json\n" + json.dumps(good_scan) + "\n```"], max_requests=4)
    scan_case("invalid JSON is retried once", ["{not json", json.dumps({"compile_requests": []})])
    scan_case("schema violation is retried once", [json.dumps({"compile_requests": [{"evidence_steps": [1]}]}), "{}"])
    scan_case("two invalid replies give an empty output", ["nope", "[]"])
    scan_case("a JSON array is not an object", ["[1, 2]", "{}"])

    good_compile = {
        "carrier_edits": [
            {"candidate_id": "C1", "carrier_type": EO, "subject": "src/parser.py", "summary": "patched", "x": 1}
        ],
        "execution_context": {"current_focus": ["verify"], "obligations": [{"obligation_id": "o3", "text": "t"}]},
    }

    def compile_case(name: str, replies: list[str]) -> None:
        llm = ScriptedRoleLLM(list(replies))
        out = Compiler(llm).compile(EvidencePackage.model_validate(package), ExecutionContext.model_validate(ec), tail)
        cases.append(
            case(
                "compiler_compile",
                name,
                {"package": package, "ec": ec, "live_tail_text": tail, "replies": replies},
                {"output": out.model_dump(mode="json"), "calls": llm.usage.calls},
            )
        )

    compile_case("valid reply", [json.dumps(good_compile)])
    compile_case("model abstains", [json.dumps({"execution_context": {}, "abstain_reason": "no evidence"})])
    compile_case("missing execution_context is retried", [json.dumps({"carrier_edits": []}), json.dumps(good_compile)])
    compile_case("invalid output abstains and keeps the context", ["bad", "worse"])
    return cases


MODULES = {
    "registry": registry_cases,
    "validator": validator_cases,
    "view": view_cases,
    "roles": roles_cases,
}


def render_all() -> dict[str, str]:
    """File name -> JSON text for every fixture file."""
    files: dict[str, str] = {}
    for module, build in MODULES.items():
        data = {"format": FORMAT, "module": module, "cases": build()}
        files[f"{module}.json"] = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the committed fixtures are out of date")
    args = parser.parse_args()
    files = render_all()
    if args.check:
        stale = [n for n, text in files.items() if not (OUT_DIR / n).is_file() or (OUT_DIR / n).read_text() != text]
        if stale:
            print(f"out of date: {', '.join(stale)}; run scripts/export_parity_fixtures.py", file=sys.stderr)
            return 1
        print(f"parity fixtures up to date ({len(files)} files)")
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (OUT_DIR / name).write_text(text)
    print(f"wrote {len(files)} files to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
