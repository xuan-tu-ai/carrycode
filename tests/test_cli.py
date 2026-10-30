"""`carrycode run`: model resolution, config building, and an offline run through the CLI."""

import json
from pathlib import Path

import pytest
import typer
from minisweagent.models.test_models import DeterministicToolcallModel, make_toolcall_output
from typer.testing import CliRunner

from carrycode import cli
from carrycode.agent import CarryOnAgent, InteractiveCarryOnAgent
from carrycode.compiler import Compiler
from carrycode.config import resolve_path
from carrycode.runtime import CarryOnRuntime
from carrycode.testing import ScriptedRoleLLM
from carrycode.tracker import Tracker

FINISH = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\necho done"

TRACKER_REPLY = {
    "candidate_updates": [
        {
            "candidate_id": "C1",
            "provisional_type": "information_product",
            "subject": "echo output",
            "description": "what echo printed",
            "supporting_steps": [3],
            "first_seen_step": 2,
            "last_revised_step": 3,
        }
    ],
    "compile_requests": [{"candidate_id": "C1", "evidence_steps": [3]}],
}

COMPILER_REPLY = {
    "carrier_edits": [
        {
            "candidate_id": "C1",
            "carrier_type": "information_product",
            "subject": "echo output",
            "summary": "echo a printed a",
            "claims": [{"claim_id": "K1", "proposition": "echo a prints a", "source_steps": [3]}],
        }
    ],
    "execution_context": {"current_focus": ["continue"]},
}


def tc(i: int, command: str) -> dict:
    call_id = f"call_{i}"
    tool_call = {
        "id": call_id,
        "type": "function",
        "function": {"name": "bash", "arguments": json.dumps({"command": command})},
    }
    return make_toolcall_output(f"step {i}", [tool_call], [{"command": command, "tool_call_id": call_id}])


def scripted_runtime(settings, role) -> CarryOnRuntime:
    return CarryOnRuntime(
        Tracker(ScriptedRoleLLM([TRACKER_REPLY])),
        Compiler(ScriptedRoleLLM([COMPILER_REPLY])),
        trigger_tokens=1,
    )


def test_resolve_models_runtime_defaults_to_host() -> None:
    models = cli.resolve_models("anthropic/claude-sonnet-4-6", None, None)
    assert models.host.model_name == "anthropic/claude-sonnet-4-6"
    assert models.runtime.model_name == "anthropic/claude-sonnet-4-6"
    assert models.api_key_env is None


def test_resolve_models_separate_runtime_model() -> None:
    models = cli.resolve_models("openai/gpt-5", "openai/gpt-5-mini", None)
    assert models.runtime.model_name == "openai/gpt-5-mini"


def test_resolve_models_file_price_registry_is_relative_to_the_file(tmp_path) -> None:
    (tmp_path / "prices.json").write_text("{}")
    (tmp_path / "m.yaml").write_text(
        "price_registry: prices.json\nhost: {model_name: openai/x}\nruntime: {model_name: openai/x}\n"
    )
    models = cli.resolve_models(None, None, tmp_path / "m.yaml")
    assert models.price_registry == tmp_path / "prices.json"


def test_resolve_models_repo_config_keeps_repo_root_paths() -> None:
    models = cli.resolve_models(None, None, Path("configs/models/luna.yaml"))
    assert resolve_path(models.price_registry).exists()


def test_resolve_models_needs_a_model() -> None:
    with pytest.raises(typer.BadParameter):
        cli.resolve_models(None, None, None)


def test_build_run_config(tmp_path) -> None:
    models = cli.resolve_models("openai/gpt-5", None, None)
    cfg = cli.build_run_config(
        models, tmp_path, yolo=True, step_limit=7, cost_limit=None, exit_immediately=True, output=tmp_path / "t.json"
    )
    assert cfg["agent"]["mode"] == "yolo"
    assert cfg["agent"]["step_limit"] == 7
    assert cfg["agent"]["cost_limit"] == 3.0  # mini.yaml default kept
    assert cfg["agent"]["confirm_exit"] is False
    assert cfg["environment"]["cwd"] == str(tmp_path)
    assert cfg["model"]["model_name"] == "openai/gpt-5"
    assert "cost_tracking" not in cfg["model"]  # leaves MSWEA_COST_TRACKING in charge
    assert "{{task}}" in cfg["agent"]["instance_template"]


def test_interactive_agent_query_goes_through_the_fold() -> None:
    assert InteractiveCarryOnAgent.__mro__.index(CarryOnAgent) > 1  # InteractiveAgent.query runs first


def test_cli_run_offline(tmp_path, monkeypatch) -> None:
    model = DeterministicToolcallModel(outputs=[tc(0, "echo a"), tc(1, "echo b"), tc(2, FINISH)])
    monkeypatch.setattr(cli, "get_model", lambda config: model)
    monkeypatch.setattr(cli, "make_runtime", scripted_runtime)
    out = tmp_path / "run.traj.json"

    result = CliRunner().invoke(
        cli.app,
        [
            "run",
            "say a and b",
            "-m",
            "openai/gpt-5",
            "--yolo",
            "--exit-immediately",
            "--cwd",
            str(tmp_path),
            "-o",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "fold 1 committed" in result.output
    traj = json.loads(out.read_text())
    assert traj["info"]["exit_status"] == "Submitted"
    assert traj["info"]["carryon"]["fold_stats"]["committed"] == 1
