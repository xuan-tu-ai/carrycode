from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from carrycode.config import (
    ExperimentConfig,
    RuntimeSettings,
    build_mswea_config,
    load_experiment,
    load_models,
    setup_provider,
)

EXPERIMENT_DIR = Path("configs/experiments")
EXPERIMENT_FILES = sorted(EXPERIMENT_DIR.glob("*.yaml"))


@pytest.mark.parametrize(
    "path",
    EXPERIMENT_FILES,
    ids=[p.stem for p in EXPERIMENT_FILES],
)
def test_all_experiment_configs_load(path: Path) -> None:
    exp = load_experiment(path)
    assert isinstance(exp, ExperimentConfig)
    assert exp.name == path.stem


def test_carryon_config_has_runtime() -> None:
    exp = load_experiment(Path("configs/experiments/carryon_full.yaml"))
    assert exp.runtime == RuntimeSettings(trigger_tokens=6000, max_requests_per_scan=4, use_code_checks=True)


def test_sliding_window_requires_window() -> None:
    with pytest.raises(ValidationError):
        ExperimentConfig(name="x", agent="sliding_window", models=Path("m.yaml"))


def test_carryon_requires_runtime() -> None:
    with pytest.raises(ValidationError):
        ExperimentConfig(name="x", agent="carryon", models=Path("m.yaml"))


def test_load_models() -> None:
    models = load_models(Path("configs/models/deepseek.yaml"))
    assert models.host.model_name.startswith("openai/deepseek-v4.1-flash")


def test_build_mswea_config_merges_limits_and_model() -> None:
    exp = load_experiment(Path("configs/experiments/baseline.yaml"))
    models = load_models(exp.models)
    cfg = build_mswea_config(exp, models)
    assert cfg["agent"]["step_limit"] == 250
    assert cfg["agent"]["cost_limit"] == 3.0
    assert cfg["model"]["model_name"] == models.host.model_name
    assert "instance_template" in cfg["agent"]
    assert cfg["environment"]["environment_class"] == "docker"
    assert cfg["model"]["model_kwargs"]["parallel_tool_calls"] is True


def test_deepseek_models_use_token_harbor() -> None:
    models = load_models(Path("configs/models/deepseek.yaml"))
    assert models.api_key_env == "TOKENHARBOR_API_KEY"
    assert models.host.model_kwargs["api_base"] == "https://tokenharbor.ai/v1"
    assert models.runtime.model_kwargs["api_base"] == "https://tokenharbor.ai/v1"


def test_setup_provider_copies_key_and_registers_prices(monkeypatch) -> None:
    import litellm

    monkeypatch.setenv("TOKENHARBOR_API_KEY", "thk_test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    models = load_models(Path("configs/models/deepseek.yaml"))
    setup_provider(models)
    assert os.environ["OPENAI_API_KEY"] == "thk_test"
    assert litellm.model_cost[models.host.model_name]["input_cost_per_token"] > 0


def test_setup_provider_requires_key(monkeypatch) -> None:
    monkeypatch.delenv("TOKENHARBOR_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TOKENHARBOR_API_KEY"):
        setup_provider(load_models(Path("configs/models/deepseek.yaml")))
