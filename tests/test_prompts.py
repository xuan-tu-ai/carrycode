from __future__ import annotations

from pathlib import Path

import carrycode.prompts
from carrycode.prompts import load_prompt
from carrycode.tracker import TrackerOutput


def test_load_tracker_prompt():
    prompt = load_prompt("tracker")
    assert isinstance(prompt, str)
    assert 1500 <= len(prompt) <= 8000
    assert "JSON" in prompt


def test_tracker_prompt_names_all_fields():
    prompt = load_prompt("tracker")
    expected_fields = [
        "candidate_updates",
        "compile_requests",
        "resolved_obligation_ids",
        "candidate_id",
        "provisional_type",
        "subject",
        "description",
        "supporting_steps",
        "target_carrier_id",
        "first_seen_step",
        "last_revised_step",
        "evidence_steps",
        "checks",
        "check_name",
        "target",
        "expected",
        "external_object",
        "information_product",
        "situated_state",
        "file_exists",
        "git_diff_nonempty",
        "python_compiles",
        "test_outcome",
    ]
    for field in expected_fields:
        assert field in prompt, f"Missing field {field!r} in tracker prompt"


def test_tracker_prompt_example_is_valid():
    prompt = load_prompt("tracker")
    lines = prompt.splitlines()
    start_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "```json":
            start_idx = i + 1
            break
    assert start_idx is not None, "No ```json code block found"

    end_idx = None
    for i in range(start_idx, len(lines)):
        if lines[i].strip() == "```":
            end_idx = i
            break
    assert end_idx is not None, "Closing ``` not found"

    json_text = "\n".join(lines[start_idx:end_idx])
    parsed = TrackerOutput.model_validate_json(json_text)
    assert len(parsed.candidate_updates) == 1
    assert len(parsed.compile_requests) == 1


def test_prompts_do_not_reuse_paper_wording():
    forbidden = [
        "duty a",
        "ledger",
        "readiness judge",
        "semantic carry rule",
        "opaque-handle",
        "residual-ec",
        "sealed, bounded",
        "simulate deletion",
    ]
    prompts_dir = Path(carrycode.prompts.__file__).parent
    md_files = [f for f in prompts_dir.glob("*.md") if f.name != "README.md"]
    assert md_files, "No prompt markdown files found"
    for md_file in md_files:
        text = md_file.read_text(encoding="utf-8").lower()
        for phrase in forbidden:
            assert phrase not in text, f"Found forbidden phrase {phrase!r} in {md_file.name}"
