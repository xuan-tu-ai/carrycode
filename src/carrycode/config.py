"""Typed loaders for experiment and model YAML configs.

Provides pydantic models for ``configs/experiments/*.yaml`` and
``configs/models/*.yaml``, plus a helper that merges them into the
dict mini-swe-agent expects.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from minisweagent.config import get_config_from_spec
from minisweagent.utils.serialize import recursive_merge
from pydantic import BaseModel, Field, model_validator

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
"""Relative paths in config files are resolved against the repository root."""


class RoleModelConfig(BaseModel):
    model_name: str
    model_kwargs: dict[str, Any] = Field(default_factory=dict)
    cost_tracking: Literal["default", "ignore_errors"] = "default"


class ModelsConfig(BaseModel):
    host: RoleModelConfig
    runtime: RoleModelConfig


class RuntimeSettings(BaseModel):
    trigger_tokens: int = 6000
    max_requests_per_scan: int = 4
    use_code_checks: bool = True


class ExperimentConfig(BaseModel):
    name: str
    agent: Literal["default", "sliding_window", "carryon"]
    models: Path
    agent_config: str = "swebench"
    step_limit: int = 250
    cost_limit: float = 3.0
    window_messages: int | None = None
    runtime: RuntimeSettings | None = None

    @model_validator(mode="after")
    def _check_agent_fields(self) -> ExperimentConfig:
        if self.agent == "sliding_window" and self.window_messages is None:
            raise ValueError("sliding_window agent requires window_messages")
        if self.agent == "carryon" and self.runtime is None:
            raise ValueError("carryon agent requires runtime settings")
        return self


def resolve_path(path: Path) -> Path:
    """Return *path* unchanged if absolute, otherwise resolve it against the repo root."""
    return path if path.is_absolute() else REPO_ROOT / path


def load_experiment(path: Path) -> ExperimentConfig:
    """Load and validate an experiment config YAML file."""
    data = yaml.safe_load(resolve_path(path).read_text())
    return ExperimentConfig(**data)


def load_models(path: Path) -> ModelsConfig:
    """Load and validate a models config YAML file."""
    data = yaml.safe_load(resolve_path(path).read_text())
    return ModelsConfig(**data)


def build_mswea_config(exp: ExperimentConfig, models: ModelsConfig) -> dict:
    """Build the full mini-swe-agent config dict for one experiment."""
    base = get_config_from_spec(exp.agent_config)
    return recursive_merge(
        base,
        {
            "agent": {"step_limit": exp.step_limit, "cost_limit": exp.cost_limit},
            "model": {
                "model_name": models.host.model_name,
                "model_kwargs": models.host.model_kwargs,
                "cost_tracking": models.host.cost_tracking,
            },
        },
    )
