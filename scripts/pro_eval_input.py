"""Convert a mini-swe-agent preds.json into the patch file the SWE-bench Pro evaluator reads.

See :func:`carrycode.swebench.to_pro_patches` for the format.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from carrycode.swebench import to_pro_patches

app = typer.Typer(add_completion=False)


@app.command()
def main(
    preds: Path = typer.Option(..., help="runs/<experiment>/preds.json"),
    prefix: str = typer.Option(..., help="Prefix the evaluator uses to name this run's outputs"),
    out: Path = typer.Option(..., help="Patch file for the evaluator's --patch_path"),
) -> None:
    """Write the SWE-bench Pro evaluator input for one run."""
    patches = to_pro_patches(json.loads(preds.read_text()), prefix)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(patches, indent=2))
    print(f"wrote {len(patches)} patches to {out}")


if __name__ == "__main__":
    app()
