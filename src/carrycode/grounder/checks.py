"""Coding checks for the Grounder. All run through mini-swe-agent's `env.execute`.

Every check must be read-only: wrap them with `repo_unchanged` (git_status before/after).
The test check is the main addition over the paper's OSWorld checks (Table 6).
"""

from __future__ import annotations

import shlex

from carrycode.grounder.base import CheckResult, Verdict

SAFE_ENV = "PYTHONDONTWRITEBYTECODE=1"


def _run(env, command: str, timeout: int | None = None) -> dict:
    kwargs = {"timeout": timeout} if timeout else {}
    return env.execute({"command": command}, **kwargs)


def _tail(text: str, limit: int = 400) -> str:
    return text if len(text) <= limit else "..." + text[-limit:]


class FileExists:
    name = "file_exists"

    def run(self, env, target: str, expected: str | None = None) -> CheckResult:
        out = _run(env, f"test -f {shlex.quote(target)}")
        verdict = Verdict.SUPPORTED if out["returncode"] == 0 else Verdict.CONTRADICTED
        return CheckResult(check_name=self.name, target=target, verdict=verdict, observation=str(out["returncode"]))


class GitDiffNonEmpty:
    """The file differs from the task's starting commit."""

    name = "git_diff_nonempty"

    def run(self, env, target: str, expected: str | None = None) -> CheckResult:
        out = _run(env, f"git diff --stat -- {shlex.quote(target)}")
        if out["returncode"] != 0:
            verdict = Verdict.UNKNOWN
        else:
            verdict = Verdict.SUPPORTED if out["output"].strip() else Verdict.CONTRADICTED
        return CheckResult(check_name=self.name, target=target, verdict=verdict, observation=_tail(out["output"]))


class PythonCompiles:
    name = "python_compiles"

    def run(self, env, target: str, expected: str | None = None) -> CheckResult:
        # compile() in memory: py_compile would write a .pyc file.
        code = f"compile(open({target!r}).read(), {target!r}, 'exec')"
        out = _run(env, f"{SAFE_ENV} python -c {shlex.quote(code)}")
        verdict = Verdict.SUPPORTED if out["returncode"] == 0 else Verdict.CONTRADICTED
        return CheckResult(check_name=self.name, target=target, verdict=verdict, observation=_tail(out["output"]))


class TestOutcomeCheck:
    """Re-run a recorded test command and compare with the recorded outcome.

    `target` is a pytest node id; `expected` is "pass" or "fail".
    """

    name = "test_outcome"
    __test__ = False  # not a pytest test class

    def __init__(self, timeout: int = 120) -> None:
        self.timeout = timeout

    def run(self, env, target: str, expected: str | None = None) -> CheckResult:
        cmd = f"{SAFE_ENV} python -m pytest -x -q -p no:cacheprovider {shlex.quote(target)}"
        try:
            out = _run(env, cmd, timeout=self.timeout)
        except Exception as e:  # timeout or environment failure: undecidable, not a contradiction
            return CheckResult(check_name=self.name, target=target, verdict=Verdict.UNKNOWN, observation=str(e))
        observed = "pass" if out["returncode"] == 0 else "fail"
        if expected is None:
            verdict = Verdict.UNKNOWN
        else:
            verdict = Verdict.SUPPORTED if observed == expected else Verdict.CONTRADICTED
        return CheckResult(
            check_name=self.name, target=target, verdict=verdict, observation=f"{observed}: {_tail(out['output'])}"
        )


def git_status(env) -> str:
    """Snapshot used to assert that a batch of checks left the repo unchanged."""
    return _run(env, "git status --porcelain")["output"]
