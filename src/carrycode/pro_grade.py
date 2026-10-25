"""Grade predictions with the SWE-bench Pro V2 verifier on local Docker.

Each task ships its verifier under `<tasks_root>/<instance_id>/` (`task.toml`, `tests/`, `solution/`).
Files travel through stdin (`tar`, `cat`), not bind mounts or `docker cp`, because a snap Docker
cannot read the host's /tmp.
"""

from __future__ import annotations

import io
import re
import subprocess
import tarfile
import tomllib
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

DEFAULT_TIMEOUT_SEC = 3000

Runner = Callable[..., subprocess.CompletedProcess]
"""Same signature as `subprocess.run`; tests pass a fake."""


class Grade(BaseModel):
    instance_id: str
    reward: int | None
    """1 resolved, 0 not, None if grading itself failed."""
    patch_applied: bool
    required: int | None = None
    passed: int | None = None
    error: str = ""


def _load_task(task_dir: Path) -> dict:
    return tomllib.loads((task_dir / "task.toml").read_text())


def task_image(task_dir: Path) -> str:
    """The instance image named in the task's `task.toml`."""
    return _load_task(task_dir)["environment"]["docker_image"]


def tests_tar(task_dir: Path) -> bytes:
    """In-memory tar of `task_dir/tests`, stored under the archive name `tests`."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        tar.add(task_dir / "tests", arcname="tests")
    return buf.getvalue()


def _text(proc: subprocess.CompletedProcess) -> str:
    out = proc.stdout or b""
    return out.decode(errors="replace") if isinstance(out, bytes) else str(out)


def _stderr(proc: subprocess.CompletedProcess) -> str:
    err = proc.stderr or b""
    return err.decode(errors="replace") if isinstance(err, bytes) else str(err)


def _count(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def grade_patch(task_dir: Path, instance_id: str, patch: str, run: Runner = subprocess.run) -> Grade:
    """Apply `patch` in a fresh container of the task image and run the V2 verifier.

    A patch that does not apply scores 0 without running the tests. A problem with grading itself
    (missing task, Docker failure, no reward file) gives `reward=None`.
    """

    def failed(error: str, applied: bool = False) -> Grade:
        return Grade(instance_id=instance_id, reward=None, patch_applied=applied, error=error)

    try:
        task = _load_task(task_dir)
        image = task["environment"]["docker_image"]
        timeout = int(task.get("verifier", {}).get("timeout_sec", DEFAULT_TIMEOUT_SEC))
        tar_bytes = tests_tar(task_dir)
    except (OSError, KeyError, ValueError, tomllib.TOMLDecodeError) as e:
        return failed(f"task unreadable: {e}")

    started = run(
        ["docker", "run", "-d", "--entrypoint", "/bin/bash", image, "-c", "sleep 3600"],
        capture_output=True,
    )
    cid = _text(started).strip()
    if started.returncode != 0 or not cid:
        return failed(f"docker run failed ({started.returncode}): {cid[-200:]}")

    try:
        copied = run(["docker", "exec", "-i", cid, "tar", "-C", "/", "-xf", "-"], capture_output=True, input=tar_bytes)
        if copied.returncode != 0:
            return failed(f"copying tests failed: {_text(copied)[-200:]}")
        applied = False
        if patch.strip():
            run(
                ["docker", "exec", "-i", cid, "bash", "-c", "cat > /tmp/model.patch"],
                capture_output=True,
                input=patch.encode(),
            )
            apply = run(
                ["docker", "exec", cid, "bash", "-c", "cd /app 2>/dev/null || cd /testbed; git apply /tmp/model.patch"],
                capture_output=True,
            )
            if apply.returncode != 0:
                return Grade(
                    instance_id=instance_id,
                    reward=0,
                    patch_applied=False,
                    error=f"git apply failed: {(_text(apply) + _stderr(apply)).strip()[-200:]}",
                )
            applied = True

        try:
            tests = run(["docker", "exec", cid, "bash", "/tests/test.sh"], capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return failed(f"test.sh timed out after {timeout}s", applied)
        log = _text(tests)
        required = _count(r"Required tests:\s*(\d+)", log)
        passed = _count(r"Required tests that passed:\s*(\d+)", log)

        reward_proc = run(["docker", "exec", cid, "cat", "/logs/verifier/reward.txt"], capture_output=True)
        reward_text = _text(reward_proc).strip()
        if reward_proc.returncode != 0 or reward_text not in ("0", "1"):
            return Grade(
                instance_id=instance_id,
                reward=None,
                patch_applied=applied,
                required=required,
                passed=passed,
                error=f"unreadable reward.txt: {reward_text[:100]!r}",
            )
        return Grade(
            instance_id=instance_id,
            reward=int(reward_text),
            patch_applied=applied,
            required=required,
            passed=passed,
        )
    finally:
        run(["docker", "rm", "-f", cid], capture_output=True)


def grade_preds(preds: dict, tasks_root: Path, run: Runner = subprocess.run) -> list[Grade]:
    """Grade every entry of a mini-swe-agent `preds.json`, in instance-id order."""
    return [
        grade_patch(tasks_root / iid, iid, entry.get("model_patch") or "", run=run)
        for iid, entry in sorted(preds.items())
    ]
