"""Aggregate runs into one table per experiment.

TODO(M3): per experiment, report resolved rate (from the SWE-bench harness report), mean
total tokens per task (host + runtime), mean input tokens per call, folds per task, rejected
fold rate, compiler abstain rate, and runtime wall time. Write results/summary.csv.
"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(add_completion=False)


@app.command()
def main(runs_dir: Path = typer.Option(Path("runs"))) -> None:
    raise NotImplementedError("M3: see module docstring")


if __name__ == "__main__":
    app()
