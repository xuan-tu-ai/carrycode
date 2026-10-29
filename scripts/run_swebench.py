"""Run one experiment config on SWE-bench Verified instances.

See :mod:`carrycode.swebench` for the execution logic.
"""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path

import dotenv
import typer

from carrycode.config import REPO_ROOT, build_mswea_config, load_experiment, load_models, setup_provider
from carrycode.swebench import DATASETS, load_instances, read_instance_ids, run_instance

app = typer.Typer(add_completion=False)


@app.command()
def main(
    experiment: Path = typer.Option(..., help="configs/experiments/<name>.yaml"),
    instances: Path = typer.Option(Path("data/swebench_verified_subset.txt"), help="One instance id per line"),
    out: Path = typer.Option(Path("runs"), help="Output directory"),
    workers: int = typer.Option(1, help="Parallel instances (each starts a Docker container)"),
    redo_existing: bool = typer.Option(False, help="Re-run instances already in preds.json"),
) -> None:
    """Run one experiment on a list of SWE-bench instances."""
    dotenv.load_dotenv(REPO_ROOT / ".env")

    exp = load_experiment(experiment)
    models = load_models(exp.models)
    setup_provider(models)
    cfg = build_mswea_config(exp, models)

    ids = read_instance_ids(instances)
    out_dir = out / exp.name
    preds_file = out_dir / "preds.json"
    if not redo_existing and preds_file.exists():
        preds = json.loads(preds_file.read_text())
        ids = [i for i in ids if i not in preds]

    if not ids:
        print("nothing to run")
        return

    rows = load_instances(ids, dataset=DATASETS[exp.benchmark])

    def _run(row: dict):
        return run_instance(row, exp, models, cfg, out_dir)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_run, rows))

    for res in results:
        print(f"{res.instance_id}\t{res.exit_status}\t{res.total_tokens()}\t{res.total_cost():.4f}")


if __name__ == "__main__":
    app()
