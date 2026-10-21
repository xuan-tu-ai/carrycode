"""Build the host agent for an experiment from typed config objects."""

from __future__ import annotations

from pathlib import Path

from minisweagent.agents.default import DefaultAgent

from carrycode.agent import SlidingWindowAgent
from carrycode.config import ExperimentConfig, ModelsConfig


def build_agent(
    exp: ExperimentConfig,
    models: ModelsConfig,
    mswea_config: dict,
    model,
    env,
    output_path: Path | None = None,
) -> DefaultAgent:
    """Build the host agent named by *exp.agent*.

    *mswea_config* comes from :func:`carrycode.config.build_mswea_config`.
    """
    agent_kwargs = dict(mswea_config["agent"])
    if output_path is not None:
        agent_kwargs["output_path"] = output_path

    if exp.agent == "default":
        return DefaultAgent(model, env, **agent_kwargs)
    if exp.agent == "sliding_window":
        return SlidingWindowAgent(model, env, window_messages=exp.window_messages, **agent_kwargs)
    if exp.agent == "carryon":
        raise NotImplementedError("carryon agent: see T017")
    raise ValueError(f"unknown agent type: {exp.agent!r}")
