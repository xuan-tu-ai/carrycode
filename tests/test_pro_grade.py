"""Tests for the local SWE-bench Pro V2 grader (offline: a fake runner stands in for Docker)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tarfile
from io import BytesIO
from pathlib import Path

import pytest

from carrycode import pro_grade
from carrycode.pro_grade import grade_patch, grade_preds


def _proc(out: str = "", code: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=out.encode(), stderr=b"")


class FakeRunner:
    """Records every call; `results` maps a substring of the joined command to its CompletedProcess."""

    def __init__(self, results: dict[str, subprocess.CompletedProcess]):
        self.results = results
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        joined = " ".join(cmd)
        for key, proc in self.results.items():
            if key in joined:
                return proc
        return _proc()

    def commands(self) -> list[str]:
        return [" ".join(c) for c, _ in self.calls]


@pytest.fixture
def task_dir(tmp_path: Path) -> Path:
    d = tmp_path / "inst1"
    (d / "tests").mkdir(parents=True)
    (d / "tests" / "test.sh").write_text("echo hi\n")
    (d / "task.toml").write_text(
        '[environment]\ndocker_image = "ghcr.io/scaleapi/swe-bench_pro-v2:inst1"\n\n[verifier]\ntimeout_sec = 77\n'
    )
    return d


def _ok_results() -> dict[str, subprocess.CompletedProcess]:
    return {
        "docker run": _proc("cid123\n"),
        "git apply": _proc(),
        "test.sh": _proc("Required tests: 59\nRequired tests that passed: 59\nRESULT: PASSED\n"),
        "reward.txt": _proc("1\n"),
    }


def test_grade_patch_resolved(task_dir: Path) -> None:
    run = FakeRunner(_ok_results())
    g = grade_patch(task_dir, "inst1", "diff --git a b\n", run=run)
    assert (g.reward, g.patch_applied, g.required, g.passed) == (1, True, 59, 59)
    assert run.commands()[-1] == "docker rm -f cid123"
    assert all(kw.get("capture_output") for _, kw in run.calls)
    cmds = run.commands()
    assert not any("-v" in c for c, _ in run.calls) and not any("docker cp" in c for c in cmds)
    inputs = {" ".join(c): kw["input"] for c, kw in run.calls if "input" in kw}
    assert len(inputs) == 2
    assert inputs[next(c for c in inputs if "tar" in c)] == pro_grade.tests_tar(task_dir)
    assert inputs[next(c for c in inputs if "model.patch" in c)] == b"diff --git a b\n"
    test_call = next(kw for c, kw in run.calls if "test.sh" in " ".join(c))
    assert test_call["timeout"] == 77


def test_grade_patch_apply_failure(task_dir: Path) -> None:
    results = _ok_results() | {"git apply": _proc("error: patch failed", 1)}
    run = FakeRunner(results)
    g = grade_patch(task_dir, "inst1", "bad", run=run)
    assert (g.reward, g.patch_applied) == (0, False)
    assert not any("test.sh" in c for c in run.commands())
    assert run.commands()[-1] == "docker rm -f cid123"


def test_grade_patch_empty_skips_apply(task_dir: Path) -> None:
    run = FakeRunner(_ok_results() | {"reward.txt": _proc("0\n")})
    g = grade_patch(task_dir, "inst1", "  \n", run=run)
    assert g.reward == 0
    assert not any("git apply" in c for c in run.commands())
    assert any("test.sh" in c for c in run.commands())


def test_grade_patch_docker_failure(task_dir: Path) -> None:
    run = FakeRunner({"docker run": _proc("no such image", 125)})
    g = grade_patch(task_dir, "inst1", "diff", run=run)
    assert g.reward is None
    assert g.error
    assert not any("docker rm" in c for c in run.commands())


def test_grade_patch_missing_task_dir(tmp_path: Path) -> None:
    run = FakeRunner({})
    g = grade_patch(tmp_path / "nope", "nope", "diff", run=run)
    assert g.reward is None and g.error
    assert run.calls == []


def test_grade_preds_in_id_order(task_dir: Path) -> None:
    run = FakeRunner(_ok_results())
    preds = {"b": {"model_patch": ""}, "inst1": {"model_patch": "diff"}}
    grades = grade_preds(preds, task_dir.parent, run=run)
    assert [g.instance_id for g in grades] == ["b", "inst1"]
    assert grades[0].reward is None  # no task directory for "b"
    assert grades[1].reward == 1


def test_task_image_and_tar(task_dir: Path) -> None:
    assert pro_grade.task_image(task_dir) == "ghcr.io/scaleapi/swe-bench_pro-v2:inst1"
    with tarfile.open(fileobj=BytesIO(pro_grade.tests_tar(task_dir))) as tar:
        assert "tests/test.sh" in tar.getnames()


def _load_cli():
    spec = importlib.util.spec_from_file_location("grade_pro", Path("scripts/grade_pro.py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_grade_pro_cli_sanity(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from carrycode.pro_grade import Grade

    module = _load_cli()
    tasks = tmp_path / "tasks"
    (tasks / "inst1" / "solution").mkdir(parents=True)
    (tasks / "inst1" / "solution" / "gold_patch.diff").write_text("GOLD")
    preds = tmp_path / "preds.json"
    preds.write_text(json.dumps({"inst1": {"model_patch": "x"}}))

    def fake_grade(task_dir, iid, patch, run=None):
        return Grade(instance_id=iid, reward=1 if patch == "GOLD" else 0, patch_applied=bool(patch))

    monkeypatch.setattr(module, "grade_patch", fake_grade)
    result = CliRunner().invoke(module.app, ["--preds", str(preds), "--tasks", str(tasks), "--sanity"])
    assert result.exit_code == 0, result.output
    assert "SANITY OK" in result.output

    monkeypatch.setattr(
        module, "grade_patch", lambda t, i, p, run=None: Grade(instance_id=i, reward=0, patch_applied=False)
    )
    result = CliRunner().invoke(module.app, ["--preds", str(preds), "--tasks", str(tasks), "--sanity"])
    assert result.exit_code == 1
    assert "SANITY FAILED" in result.output
