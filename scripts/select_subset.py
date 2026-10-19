"""Pick the 20-30 SWE-bench Verified instances with the longest baseline trajectories.

TODO(M3): read baseline `*.traj.json` files, rank by number of model calls (or estimated
tokens), write the chosen ids to data/swebench_verified_subset.txt.
"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(add_completion=False)


@app.command()
def main(
    baseline_dir: Path = typer.Option(..., help="runs/baseline"),
    n: int = typer.Option(30, help="How many instances to keep"),
    out: Path = typer.Option(Path("data/swebench_verified_subset.txt")),
) -> None:
    raise NotImplementedError("M3: see module docstring")


if __name__ == "__main__":
    app()
