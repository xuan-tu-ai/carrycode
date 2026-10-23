"""Tests for the SWE-bench runner library (offline, no Docker)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from minisweagent.environments.local import LocalEnvironment
from minisweagent.models.test_models import DeterministicModel, make_output

from carrycode.config import build_mswea_config, load_experiment, load_models
from carrycode.metrics import TaskUsage
from carrycode.swebench import load_instances, read_instance_ids, run_instance, task_text


def _baseline():
    exp = load_experiment(Path("configs/experiments/baseline.yaml"))
    models = load_models(exp.models)
    cfg = build_mswea_config(exp, models)
    return exp, models, cfg


def test_read_instance_ids_skips_comments_and_blanks(tmp_path: Path) -> None:
    p = tmp_path / "ids.txt"
    p.write_text("# c\n\na__b-1\n  c__d-2  \n")
    assert read_instance_ids(p) == ["a__b-1", "c__d-2"]


def test_run_instance_writes_traj_preds_and_usage(tmp_path: Path) -> None:
    exp, models, cfg = _baseline()
    instance = {"instance_id": "repo__x-1", "problem_statement": "fix it"}
    usage = run_instance(
        instance,
        exp,
        models,
        cfg,
        tmp_path,
        model_factory=lambda _cfg: DeterministicModel(
            outputs=[make_output("done", [{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\necho mypatch"}])]
        ),
        env_factory=lambda _cfg, _inst: LocalEnvironment(),
    )
    assert usage.exit_status == "Submitted"

    traj_path = tmp_path / "repo__x-1" / "repo__x-1.traj.json"
    assert traj_path.exists()
    traj = json.loads(traj_path.read_text())
    assert traj["instance_id"] == "repo__x-1"

    preds = json.loads((tmp_path / "preds.json").read_text())
    assert preds["repo__x-1"]["model_name_or_path"] == "baseline"
    assert preds["repo__x-1"]["model_patch"].strip() == "mypatch"

    usage_lines = (tmp_path / "usage.jsonl").read_text().strip().splitlines()
    assert len(usage_lines) == 1
    TaskUsage.model_validate_json(usage_lines[0])


def _failing_env(cfg: dict, instance: dict):
    raise RuntimeError("no docker")


def test_run_instance_records_environment_failure(tmp_path: Path) -> None:
    exp, models, cfg = _baseline()
    instance = {"instance_id": "repo__x-1", "problem_statement": "fix it"}
    usage = run_instance(
        instance,
        exp,
        models,
        cfg,
        tmp_path,
        model_factory=lambda _cfg: DeterministicModel(outputs=[]),
        env_factory=_failing_env,
    )
    assert usage.exit_status == "RuntimeError"

    preds = json.loads((tmp_path / "preds.json").read_text())
    assert preds["repo__x-1"]["model_patch"] == ""

    traj_path = tmp_path / "repo__x-1" / "repo__x-1.traj.json"
    assert not traj_path.exists()


def test_load_instances_reports_missing_ids(monkeypatch) -> None:
    fake_data = [{"instance_id": "a", "problem_statement": "p"}]

    def fake(name, split):
        return fake_data

    monkeypatch.setattr("datasets.load_dataset", fake)
    result = load_instances(["a"])
    assert len(result) == 1
    assert result[0]["instance_id"] == "a"

    with pytest.raises(ValueError, match="b"):
        load_instances(["a", "b"])


def test_task_text_pro_sections() -> None:
    instance = {
        "instance_id": "repo__x-1",
        "problem_statement": "  fix it  ",
        "requirements": "  keep the API  ",
        "interface": "  def f() -> int  ",
    }
    text = task_text(instance)
    assert text.startswith("fix it\n\n## Requirements\nkeep the API")
    assert text.index("## Requirements") < text.index("## Interface")
    assert text.endswith("## Interface\ndef f() -> int")

    assert task_text({"problem_statement": "  fix it  "}) == "fix it"
    assert task_text({"problem_statement": "fix it", "requirements": "  ", "interface": ""}) == "fix it"


def test_run_instance_sends_task_text(tmp_path: Path) -> None:
    exp, models, cfg = _baseline()
    instance = {
        "instance_id": "repo__x-2",
        "problem_statement": "fix it",
        "requirements": "keep the API",
    }
    run_instance(
        instance,
        exp,
        models,
        cfg,
        tmp_path,
        model_factory=lambda _cfg: DeterministicModel(
            outputs=[make_output("done", [{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\necho mypatch"}])]
        ),
        env_factory=lambda _cfg, _inst: LocalEnvironment(),
    )

    traj = json.loads((tmp_path / "repo__x-2" / "repo__x-2.traj.json").read_text())
    assert traj["messages"][1]["role"] == "user"
    assert "## Requirements" in traj["messages"][1]["content"]
