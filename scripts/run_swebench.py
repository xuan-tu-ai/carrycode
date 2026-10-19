"""Run one experiment config on SWE-bench Verified instances.

TODO(M0): implement by following mini-swe-agent's `run/benchmarks/swebench.py::process_instance`:
load instances with `datasets`, build the env with `get_sb_environment`, build the agent from
the experiment's `agent` field, run, and save `<out>/<name>/<instance_id>/<instance_id>.traj.json`
plus `preds.json` (compatible with the official SWE-bench evaluation harness).
"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(add_completion=False)


@app.command()
def main(
    experiment: Path = typer.Option(..., help="configs/experiments/<name>.yaml"),
    instances: Path = typer.Option(Path("data/swebench_verified_subset.txt"), help="One instance id per line"),
    out: Path = typer.Option(Path("runs"), help="Output directory"),
    workers: int = typer.Option(1, help="Parallel instances (each starts a Docker container)"),
) -> None:
    raise NotImplementedError("M0: see module docstring")


if __name__ == "__main__":
    app()
