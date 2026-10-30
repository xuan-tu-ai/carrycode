"""`carrycode run`: a CarryOn coding agent in your own repository.

Same terminal loop as mini-swe-agent's `mini` (confirm, yolo and human modes), with the CarryOn runtime
folding old history into carriers and an execution context once the live tail grows past a token budget.
"""

from __future__ import annotations

import os

os.environ.setdefault("MSWEA_SILENT_STARTUP", "1")  # carrycode prints its own banner

from pathlib import Path  # noqa: E402

import typer  # noqa: E402
from minisweagent import global_config_dir  # noqa: E402
from minisweagent.agents.interactive import console  # noqa: E402
from minisweagent.agents.utils.prompt_user import _multiline_prompt  # noqa: E402
from minisweagent.config import get_config_from_spec  # noqa: E402
from minisweagent.environments.local import LocalEnvironment  # noqa: E402
from minisweagent.models import get_model  # noqa: E402
from minisweagent.utils.serialize import recursive_merge  # noqa: E402

from carrycode import __version__  # noqa: E402
from carrycode.agent import InteractiveCarryOnAgent  # noqa: E402
from carrycode.config import ModelsConfig, RoleModelConfig, RuntimeSettings, load_models, setup_provider  # noqa: E402
from carrycode.factory import make_runtime  # noqa: E402

DEFAULT_OUTPUT = global_config_dir / "last_carrycode_run.traj.json"

app = typer.Typer(add_completion=False, no_args_is_help=True, rich_markup_mode="rich")


@app.callback()
def _main() -> None:
    """carrycode: CarryOn context for coding agents (arXiv:2610.18784)."""


def resolve_models(model: str | None, runtime_model: str | None, models_file: Path | None) -> ModelsConfig:
    """Models from `--models FILE`, or from `--model` (and `--runtime-model`, which defaults to `--model`)."""
    if models_file is not None:
        models = load_models(models_file.resolve())
        if models.price_registry and not models.price_registry.is_absolute():
            # Next to the models file if it is there (an installed tool has no repository root);
            # otherwise keep the repo-root rule used by configs/models/.
            beside = models_file.resolve().parent / models.price_registry
            if beside.exists():
                models.price_registry = beside
        return models
    if not model:
        raise typer.BadParameter("pass --model (e.g. anthropic/claude-sonnet-4-6) or --models FILE")
    return ModelsConfig(
        host=RoleModelConfig(model_name=model),
        runtime=RoleModelConfig(model_name=runtime_model or model, model_kwargs={"drop_params": True}),
    )


def build_run_config(
    models: ModelsConfig,
    cwd: Path,
    *,
    yolo: bool,
    step_limit: int | None,
    cost_limit: float | None,
    exit_immediately: bool,
    output: Path | None,
) -> dict:
    """mini-swe-agent's builtin `mini.yaml`, with the host model, limits and working directory applied."""
    agent: dict = {"output_path": output}
    if yolo:
        agent["mode"] = "yolo"
    if step_limit is not None:
        agent["step_limit"] = step_limit
    if cost_limit is not None:
        agent["cost_limit"] = cost_limit
    if exit_immediately:
        agent["confirm_exit"] = False
    model: dict = {"model_name": models.host.model_name}
    if models.host.cost_tracking != "default":  # otherwise MSWEA_COST_TRACKING still applies
        model["cost_tracking"] = models.host.cost_tracking
    if models.host.model_kwargs:
        model["model_kwargs"] = models.host.model_kwargs
    return recursive_merge(
        get_config_from_spec("mini"),
        {"agent": agent, "model": model, "environment": {"cwd": str(cwd)}},
    )


@app.command()
def run(
    task: str | None = typer.Argument(
        None, help="What the agent should do. Omit to type it interactively.", show_default=False
    ),
    model: str | None = typer.Option(
        None,
        "-m",
        "--model",
        help="LiteLLM model id for the agent, e.g. anthropic/claude-sonnet-4-6, openai/gpt-5.",
        show_default=False,
    ),
    runtime_model: str | None = typer.Option(
        None, "--runtime-model", help="Model for the Tracker and Compiler. Defaults to --model.", show_default=False
    ),
    models_file: Path | None = typer.Option(
        None,
        "--models",
        help="Models YAML (see configs/models/); overrides --model.",
        show_default=False,
        rich_help_panel="Advanced",
    ),
    cwd: Path = typer.Option(Path("."), "--cwd", help="Repository to work in."),
    yolo: bool = typer.Option(False, "-y", "--yolo", help="Run commands without asking for confirmation."),
    cost_limit: float | None = typer.Option(
        None, "-l", "--cost-limit", help="Stop after this many dollars (default 3). 0 disables.", show_default=False
    ),
    step_limit: int | None = typer.Option(
        None, "--step-limit", help="Stop after this many model calls. 0 disables (default).", show_default=False
    ),
    trigger_tokens: int = typer.Option(
        24000, "--trigger-tokens", help="Fold when the live tail reaches this many tokens."
    ),
    keep_recent_tokens: int = typer.Option(8000, "--keep-recent-tokens", help="Raw recent history kept after a fold."),
    output: Path = typer.Option(
        DEFAULT_OUTPUT, "-o", "--output", help="Trajectory file (full log, carriers, fold events)."
    ),
    exit_immediately: bool = typer.Option(
        False, "--exit-immediately", help="Exit when the agent finishes instead of asking for a new task."
    ),
) -> None:
    """Run a CarryOn coding agent in a local repository. Commands run on your machine, so review them."""
    models = resolve_models(model, runtime_model, models_file)
    setup_provider(models)
    cwd = cwd.resolve()
    config = build_run_config(
        models,
        cwd,
        yolo=yolo,
        step_limit=step_limit,
        cost_limit=cost_limit,
        exit_immediately=exit_immediately,
        output=output,
    )
    settings = RuntimeSettings(trigger_tokens=trigger_tokens, keep_recent_tokens=keep_recent_tokens)

    console.print(
        f"[bold blue]carrycode[/bold blue] {__version__} · agent [bold]{models.host.model_name}[/bold] · "
        f"runtime [bold]{models.runtime.model_name}[/bold] · repo [bold]{cwd}[/bold]",
        highlight=False,
    )
    if task is None:
        console.print("[bold yellow]What do you want to do?")
        task = _multiline_prompt()

    agent = InteractiveCarryOnAgent(
        get_model(config=config["model"]),
        LocalEnvironment(**config["environment"]),
        runtime=make_runtime(settings, models.runtime),
        **config["agent"],
    )
    result = agent.run(task)
    stats = agent.runtime.stats
    console.print(
        f"\n[bold blue]carryon[/bold blue]: {result.get('exit_status', '?')} after {agent.n_calls} steps, "
        f"${agent.cost:.2f}; folds committed {stats.committed}, rejected {len(stats.rejected)}.\n"
        f"Trajectory: [bold green]{output}[/bold green]",
        highlight=False,
    )


if __name__ == "__main__":
    app()
