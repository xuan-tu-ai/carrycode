"""Build the host agent for an experiment from typed config objects."""

from __future__ import annotations

from pathlib import Path

from minisweagent.agents.default import DefaultAgent

from carrycode.agent import CarryOnAgent, SlidingWindowAgent
from carrycode.compiler import Compiler
from carrycode.config import ExperimentConfig, ModelsConfig, RoleModelConfig, RuntimeSettings
from carrycode.llm import RoleLLM
from carrycode.runtime import CarryOnRuntime
from carrycode.tracker import Tracker


def build_runtime(exp: ExperimentConfig, models: ModelsConfig) -> CarryOnRuntime:
    """Tracker and Compiler share the runtime model (docs/decisions.md: one model for both roles)."""
    if exp.runtime is None:
        raise ValueError(f"experiment {exp.name} has no runtime settings")
    return make_runtime(exp.runtime, models.runtime)


def make_runtime(settings: RuntimeSettings, role: RoleModelConfig) -> CarryOnRuntime:
    """Build the runtime from its settings and the model shared by the Tracker and the Compiler."""
    tracker = Tracker(
        RoleLLM(role.model_name, role.model_kwargs),
        max_requests_per_scan=settings.max_requests_per_scan,
    )
    compiler = Compiler(RoleLLM(role.model_name, role.model_kwargs))
    return CarryOnRuntime(
        tracker,
        compiler,
        trigger_tokens=settings.trigger_tokens,
        keep_recent_tokens=settings.keep_recent_tokens,
        use_code_checks=settings.use_code_checks,
    )


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
        return CarryOnAgent(model, env, runtime=build_runtime(exp, models), **agent_kwargs)
    raise ValueError(f"unknown agent type: {exp.agent!r}")
