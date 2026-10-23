"""Factory tests: build_agent returns the right class with correct config."""

from __future__ import annotations

from pathlib import Path

import pytest
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.models.test_models import DeterministicModel, make_output

from carrycode.agent import CarryOnAgent, SlidingWindowAgent
from carrycode.config import build_mswea_config, load_experiment, load_models
from carrycode.factory import build_agent, build_runtime


def _load(name: str):
    exp = load_experiment(Path(f"configs/experiments/{name}"))
    models = load_models(exp.models)
    cfg = build_mswea_config(exp, models)
    return exp, models, cfg


def test_build_default_agent() -> None:
    exp, models, cfg = _load("baseline.yaml")
    agent = build_agent(exp, models, cfg, DeterministicModel(outputs=[]), LocalEnvironment())
    assert type(agent) is DefaultAgent
    assert agent.config.step_limit == 250


def test_build_sliding_window_agent() -> None:
    exp, models, cfg = _load("sliding_window.yaml")
    agent = build_agent(exp, models, cfg, DeterministicModel(outputs=[]), LocalEnvironment())
    assert isinstance(agent, SlidingWindowAgent)
    assert agent.config.window_messages == 30


def test_default_agent_runs_offline() -> None:
    exp, models, cfg = _load("baseline.yaml")
    agent = build_agent(
        exp,
        models,
        cfg,
        DeterministicModel(
            outputs=[make_output("done", [{"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\necho patch"}])]
        ),
        LocalEnvironment(),
    )
    assert agent.run("task")["exit_status"] == "Submitted"


def test_build_carryon_agent() -> None:
    exp, models, cfg = _load("carryon_full.yaml")
    agent = build_agent(exp, models, cfg, DeterministicModel(outputs=[]), LocalEnvironment())
    assert isinstance(agent, CarryOnAgent)
    assert agent.runtime.trigger_tokens == 6000
    assert agent.runtime.tracker.max_requests_per_scan == 4
    assert agent.runtime.tracker.llm is not agent.runtime.compiler.llm


def test_no_code_checks_config() -> None:
    exp, models, cfg = _load("carryon_no_code_checks.yaml")
    agent = build_agent(exp, models, cfg, DeterministicModel(outputs=[]), LocalEnvironment())
    assert agent.runtime.use_code_checks is False


def test_runtime_uses_runtime_model() -> None:
    exp, models, cfg = _load("carryon_full.yaml")
    agent = build_agent(exp, models, cfg, DeterministicModel(outputs=[]), LocalEnvironment())
    assert agent.runtime.compiler.llm.model_name == load_models(exp.models).runtime.model_name


@pytest.mark.parametrize("path", sorted(Path("configs/experiments").glob("*.yaml")), ids=lambda p: p.stem)
def test_every_experiment_builds(path: Path) -> None:
    exp, models, cfg = _load(path.name)
    build_agent(exp, models, cfg, DeterministicModel(outputs=[]), LocalEnvironment())


def test_build_runtime_requires_settings() -> None:
    exp, models, _ = _load("baseline.yaml")
    with pytest.raises(ValueError, match="runtime settings"):
        build_runtime(exp, models)


def test_output_path_is_passed(tmp_path: Path) -> None:
    exp, models, cfg = _load("baseline.yaml")
    out = tmp_path / "t.traj.json"
    agent = build_agent(exp, models, cfg, DeterministicModel(outputs=[]), LocalEnvironment(), output_path=out)
    assert agent.config.output_path == out
