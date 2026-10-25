from carrycode.grounder import CheckResult, Verdict, aggregate
from carrycode.grounder.checks import CommandExit, GitDiffNonEmpty, TestOutcomeCheck


def r(v: Verdict) -> CheckResult:
    return CheckResult(check_name="x", target="t", verdict=v, observation="")


def test_aggregate_rules():
    assert aggregate([r(Verdict.SUPPORTED), r(Verdict.SUPPORTED)]) == Verdict.SUPPORTED
    assert aggregate([r(Verdict.SUPPORTED), r(Verdict.UNKNOWN)]) == Verdict.UNKNOWN
    assert aggregate([r(Verdict.UNKNOWN), r(Verdict.CONTRADICTED)]) == Verdict.CONTRADICTED
    assert aggregate([]) == Verdict.UNKNOWN


class FakeEnv:
    """Stands in for a mini-swe-agent Environment: maps command substrings to results."""

    def __init__(self, responses: dict[str, dict]):
        self.responses = responses
        self.commands: list[str] = []

    def execute(self, action: dict, cwd: str = "", **kwargs) -> dict:
        cmd = action["command"]
        self.commands.append(cmd)
        for key, out in self.responses.items():
            if key in cmd:
                return out
        return {"output": "", "returncode": 1}


def test_git_diff_untracked_file_supported():
    env = FakeEnv({"git status": {"output": "?? src/new.ts\n", "returncode": 0}})
    assert GitDiffNonEmpty().run(env, "src/new.ts").verdict == Verdict.SUPPORTED


def test_git_diff_clean_file_contradicted():
    env = FakeEnv({"git status": {"output": "", "returncode": 0}})
    assert GitDiffNonEmpty().run(env, "src/a.py").verdict == Verdict.CONTRADICTED
    env = FakeEnv({"git status": {"output": "", "returncode": 128}})
    assert GitDiffNonEmpty().run(env, "src/a.py").verdict == Verdict.UNKNOWN


def test_git_diff_modified_file_supported():
    env = FakeEnv({"git status": {"output": " M src/a.py\n", "returncode": 0}})
    assert GitDiffNonEmpty().run(env, "src/a.py").verdict == Verdict.SUPPORTED


def test_command_exit_matches_expected():
    env = FakeEnv({"tsc": {"output": "", "returncode": 0}})
    assert CommandExit().run(env, "npx tsc --noEmit").verdict == Verdict.SUPPORTED
    env = FakeEnv({"go test": {"output": "FAIL", "returncode": 1}})
    assert CommandExit().run(env, "go test ./...", expected="1").verdict == Verdict.SUPPORTED
    env = FakeEnv({"go test": {"output": "FAIL", "returncode": 2}})
    assert CommandExit().run(env, "go test ./...", expected="0").verdict == Verdict.CONTRADICTED


def test_command_exit_bad_expected_is_unknown():
    env = FakeEnv({"go test": {"output": "", "returncode": 0}})
    assert CommandExit().run(env, "go test ./...", expected="pass").verdict == Verdict.UNKNOWN


def test_command_exit_uses_safe_env():
    env = FakeEnv({"npm test": {"output": "ok", "returncode": 0}})
    CommandExit().run(env, "npm test")
    assert env.commands[0].startswith("PYTHONDONTWRITEBYTECODE=1")


def test_test_outcome_compares_with_recorded_result():
    env = FakeEnv({"pytest": {"output": "1 passed", "returncode": 0}})
    assert TestOutcomeCheck().run(env, "tests/t.py::test_x", expected="pass").verdict == Verdict.SUPPORTED
    assert TestOutcomeCheck().run(env, "tests/t.py::test_x", expected="fail").verdict == Verdict.CONTRADICTED
    assert "no:cacheprovider" in env.commands[0]
