"""SWE-bench runner library: run one experiment config on a list of instances.

Writes per-instance trajectories, a unified ``preds.json`` for the official
SWE-bench evaluation harness, and a ``usage.jsonl`` with token/cost accounting.
"""

from __future__ import annotations

import logging
import threading
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from minisweagent.models import get_model
from minisweagent.run.benchmarks.swebench import get_sb_environment, remove_from_preds_file, update_preds_file

from carrycode.config import ExperimentConfig, ModelsConfig
from carrycode.factory import build_agent
from carrycode.metrics import TaskUsage, trajectory_usage

DATASETS = {
    "verified": "princeton-nlp/SWE-Bench_Verified",
    "pro": "ScaleAI/SWE-bench_Pro",
}
DATASET = DATASETS["verified"]
logger = logging.getLogger("carrycode.swebench")
_USAGE_LOCK = threading.Lock()


def read_instance_ids(path: Path) -> list[str]:
    """One id per line; blank lines and lines starting with '#' are skipped."""
    ids: list[str] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            ids.append(stripped)
    return ids


def load_instances(ids: list[str], dataset: str = DATASET, split: str = "test") -> list[dict]:
    """Load the rows for *ids*, in the order given. Raise ValueError naming any id not in the dataset."""
    from datasets import load_dataset

    rows = load_dataset(dataset, split=split)
    by_id = {r["instance_id"]: r for r in rows}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise ValueError(f"Instance ids not found in dataset: {missing}")
    return [by_id[i] for i in ids]


def default_model_factory(mswea_config: dict):
    return get_model(config=mswea_config.get("model", {}))


def task_text(instance: dict) -> str:
    """Problem statement, plus the Pro `requirements` and `interface` sections when present and non-empty."""
    text = str(instance.get("problem_statement") or "").strip()
    for heading, field in (("Requirements", "requirements"), ("Interface", "interface")):
        section = str(instance.get(field) or "").strip()
        if section:
            text += f"\n\n## {heading}\n{section}"
    return text


def run_instance(
    instance: dict,
    exp: ExperimentConfig,
    models: ModelsConfig,
    mswea_config: dict,
    out_dir: Path,
    *,
    model_factory: Callable[[dict], Any] = default_model_factory,
    env_factory: Callable[[dict, dict], Any] = get_sb_environment,
) -> TaskUsage:
    """Run a single SWE-bench instance and write trajectory, preds entry and usage line."""
    iid = instance["instance_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    traj_path = out_dir / iid / f"{iid}.traj.json"

    remove_from_preds_file(out_dir / "preds.json", iid)
    traj_path.unlink(missing_ok=True)

    agent = None
    env = None
    exit_status = None
    submission = ""
    extra: dict[str, Any] = {}
    traj: dict = {}

    try:
        model = model_factory(mswea_config)
        env = env_factory(mswea_config, instance)
        agent = build_agent(exp, models, mswea_config, model, env, output_path=traj_path)
        info = agent.run(task_text(instance))
        exit_status = info.get("exit_status")
        submission = info.get("submission") or ""
    except Exception as e:
        logger.exception("Instance %s failed: %s", iid, e)
        exit_status = type(e).__name__
        extra = {"traceback": traceback.format_exc(), "exception_str": str(e)}
    finally:
        if agent is not None:
            traj = agent.save(
                traj_path,
                {"info": {"exit_status": exit_status, "submission": submission, **extra}, "instance_id": iid},
            )
        update_preds_file(out_dir / "preds.json", iid, exp.name, submission)
        cleanup = getattr(env, "cleanup", None)
        if callable(cleanup):
            cleanup()

    usage = trajectory_usage(traj) if traj else TaskUsage(instance_id=iid, exit_status=str(exit_status))
    with _USAGE_LOCK:
        with open(out_dir / "usage.jsonl", "a") as f:
            f.write(usage.model_dump_json() + "\n")
    return usage
