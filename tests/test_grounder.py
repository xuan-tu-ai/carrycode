from carrycode.grounder import CheckResult, Verdict, aggregate
from carrycode.grounder.checks import GitDiffNonEmpty, TestOutcomeCheck


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


def test_git_diff_nonempty():
    env = FakeEnv({"git diff": {"output": " src/a.py | 2 +-\n", "returncode": 0}})
    assert GitDiffNonEmpty().run(env, "src/a.py").verdict == Verdict.SUPPORTED
    env = FakeEnv({"git diff": {"output": "", "returncode": 0}})
    assert GitDiffNonEmpty().run(env, "src/a.py").verdict == Verdict.CONTRADICTED


def test_test_outcome_compares_with_recorded_result():
    env = FakeEnv({"pytest": {"output": "1 passed", "returncode": 0}})
    assert TestOutcomeCheck().run(env, "tests/t.py::test_x", expected="pass").verdict == Verdict.SUPPORTED
    assert TestOutcomeCheck().run(env, "tests/t.py::test_x", expected="fail").verdict == Verdict.CONTRADICTED
    assert "no:cacheprovider" in env.commands[0]
