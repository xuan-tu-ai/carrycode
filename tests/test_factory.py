"""Factory tests: build_agent returns the right class with correct config."""

from __future__ import annotations

from pathlib import Path

import pytest
from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.models.test_models import DeterministicModel, make_output

from carrycode.agent import SlidingWindowAgent
from carrycode.config import build_mswea_config, load_experiment, load_models
from carrycode.factory import build_agent


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


def test_carryon_not_yet_supported() -> None:
    exp, models, cfg = _load("carryon_full.yaml")
    with pytest.raises(NotImplementedError):
        build_agent(exp, models, cfg, DeterministicModel(outputs=[]), LocalEnvironment())


def test_output_path_is_passed(tmp_path: Path) -> None:
    exp, models, cfg = _load("baseline.yaml")
    out = tmp_path / "t.traj.json"
    agent = build_agent(exp, models, cfg, DeterministicModel(outputs=[]), LocalEnvironment(), output_path=out)
    assert agent.config.output_path == out
