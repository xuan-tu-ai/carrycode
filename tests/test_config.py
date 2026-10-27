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

PILOT_MODEL_FILES = [
    Path("configs/models/haiku.yaml"),
    Path("configs/models/gpt6luna.yaml"),
    Path("configs/models/minimax.yaml"),
    Path("configs/models/deepseek1017.yaml"),
]
PILOT_MODEL_IDS = [p.stem for p in PILOT_MODEL_FILES]
PILOT_OUTPUT_COST_PER_TOKEN = {
    Path("configs/models/haiku.yaml"): 5e-07,
    Path("configs/models/gpt6luna.yaml"): 5e-07,
    Path("configs/models/minimax.yaml"): 6e-07,
    Path("configs/models/deepseek1017.yaml"): 1.2e-06,
}


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
    assert exp.runtime == RuntimeSettings(
        trigger_tokens=24000,
        keep_recent_tokens=8000,
        max_requests_per_scan=4,
        use_code_checks=True,
    )


@pytest.mark.parametrize(
    "config_name",
    ["carryon_full.yaml", "carryon_no_code_checks.yaml", "pilot_luna_carryon.yaml"],
)
def test_carryon_experiments_use_m2_settings(config_name: str) -> None:
    exp = load_experiment(Path("configs/experiments") / config_name)
    assert exp.runtime is not None
    assert exp.runtime.trigger_tokens == 24000
    assert exp.runtime.keep_recent_tokens == 8000


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


def test_experiments_use_haiku_via_token_harbor() -> None:
    for path in EXPERIMENT_FILES:
        if path.stem.startswith(("pilot_", "hard_")):
            continue
        models = load_models(load_experiment(path).models)
        assert models.host.model_name == "openai/claude-haiku-5.5"
        assert models.runtime.model_name == "openai/claude-haiku-5.5"
        assert models.host.model_kwargs["timeout"] == 600


def test_haiku_price_registered(monkeypatch) -> None:
    import litellm

    monkeypatch.setenv("TOKENHARBOR_API_KEY", "thk_test")
    setup_provider(load_models(Path("configs/models/haiku.yaml")))
    assert litellm.model_cost["openai/claude-haiku-5.5"]["output_cost_per_token"] == 5e-07


@pytest.mark.parametrize("path", PILOT_MODEL_FILES, ids=PILOT_MODEL_IDS)
def test_pilot_model_configs(path: Path) -> None:
    models = load_models(path)
    assert models.host.model_name == models.runtime.model_name
    assert models.api_key_env == "TOKENHARBOR_API_KEY"
    for role in (models.host, models.runtime):
        kwargs = role.model_kwargs
        assert kwargs["reasoning_effort"] == "max"
        assert kwargs["timeout"] == 600
        assert kwargs["drop_params"] is True
        assert kwargs["api_base"] == "https://tokenharbor.ai/v1"


@pytest.mark.parametrize("path", PILOT_MODEL_FILES, ids=PILOT_MODEL_IDS)
def test_pilot_prices_registered(path: Path, monkeypatch) -> None:
    import litellm

    monkeypatch.setenv("TOKENHARBOR_API_KEY", "thk_test")
    models = load_models(path)
    setup_provider(models)
    # get_model_info canonicalises provider-prefixed ids (LiteLLM has a built-in `gpt-6-luna`),
    # so it resolves the key that register_model actually wrote.
    info = litellm.get_model_info(models.host.model_name)
    assert info["output_cost_per_token"] == PILOT_OUTPUT_COST_PER_TOKEN[path]


def test_benchmark_defaults_to_verified() -> None:
    for path in EXPERIMENT_FILES:
        if path.stem.startswith(("pilot_", "hard_")):
            continue
        assert load_experiment(path).benchmark == "verified"


def test_build_mswea_config_pro_uses_app() -> None:
    exp = load_experiment(Path("configs/experiments/baseline.yaml")).model_copy(update={"benchmark": "pro"})
    models = load_models(exp.models)
    cfg = build_mswea_config(exp, models)
    assert cfg["environment"]["cwd"] == "/app"
    assert "/testbed" not in cfg["agent"]["instance_template"]
    assert "/testbed" not in cfg["agent"]["system_template"]
    assert "/app" in cfg["agent"]["instance_template"]
    assert "BASH_ENV" not in cfg["environment"]["env"]


def test_build_mswea_config_verified_unchanged() -> None:
    exp = load_experiment(Path("configs/experiments/baseline.yaml"))
    models = load_models(exp.models)
    cfg = build_mswea_config(exp, models)
    assert cfg["environment"]["cwd"] == "/testbed"
    assert "BASH_ENV" in cfg["environment"]["env"]

    build_mswea_config(exp.model_copy(update={"benchmark": "pro"}), models)
    assert build_mswea_config(exp, models) == cfg


def test_luna_config_sets_instructions_and_price(monkeypatch) -> None:
    import litellm

    monkeypatch.delenv("CHATGPT_DEFAULT_INSTRUCTIONS", raising=False)
    models = load_models(Path("configs/models/luna.yaml"))
    assert models.host.model_name == models.runtime.model_name == "chatgpt/gpt-6-luna"
    assert models.api_key_env is None
    for role in (models.host, models.runtime):
        assert role.model_kwargs["reasoning_effort"] == "max"
    setup_provider(models)
    assert os.environ["CHATGPT_DEFAULT_INSTRUCTIONS"] == "You are a helpful assistant."
    info = litellm.get_model_info("chatgpt/gpt-6-luna")
    assert info["output_cost_per_token"] == 5e-07
    # "responses" routes tool calls through the Responses bridge; "chat" hits a nonexistent Codex endpoint.
    assert info["mode"] == "responses"


@pytest.mark.parametrize("suffix", PILOT_MODEL_IDS)
def test_pilot_experiments(suffix: str) -> None:
    exp = load_experiment(EXPERIMENT_DIR / f"pilot_{suffix}.yaml")
    assert exp.name == f"pilot_{suffix}"
    assert exp.agent == "default"
    assert exp.benchmark == "pro"
    assert exp.step_limit == 150
    assert exp.cost_limit == 1.5
    assert exp.models == Path(f"configs/models/{suffix}.yaml")


def test_pro_runs_block_network() -> None:
    exp = load_experiment(Path("configs/experiments/baseline.yaml"))
    models = load_models(exp.models)
    pro = build_mswea_config(exp.model_copy(update={"benchmark": "pro"}), models)
    assert pro["environment"]["run_args"] == ["--rm", "--network", "none"]
    assert "run_args" not in build_mswea_config(exp.model_copy(update={"benchmark": "verified"}), models)["environment"]
