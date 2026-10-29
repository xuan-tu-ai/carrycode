"""Grade a preds.json with the SWE-bench Pro V2 verifier on local Docker.

See :mod:`carrycode.pro_grade` for the grading protocol.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from carrycode.pro_grade import Grade, grade_patch, grade_preds

app = typer.Typer(add_completion=False)


def _line(g: Grade) -> str:
    return f"{g.instance_id[:60]} reward={g.reward} passed={g.passed}/{g.required}"


@app.command()
def main(
    preds: Path = typer.Option(..., help="runs/<experiment>/preds.json"),
    tasks: Path = typer.Option(Path("~/SWE-bench_Pro-os/v2/tasks"), help="v2/tasks of the SWE-bench_Pro-os repo"),
    out: Path | None = typer.Option(None, help="Grades file (default: <preds dir>/pro_grades.json)"),
    sanity: bool = typer.Option(False, help="Grade each gold patch and an empty patch instead of the predictions"),
) -> None:
    """Grade predictions (or, with --sanity, the verifier itself) and write the grades as JSON."""
    tasks = tasks.expanduser()
    out = out or preds.parent / "pro_grades.json"
    data = json.loads(preds.read_text())

    if sanity:
        grades: list[Grade] = []
        ok = True
        for iid in sorted(data):
            gold = (tasks / iid / "solution" / "gold_patch.diff").read_text()
            gold_grade = grade_patch(tasks / iid, iid, gold)
            empty_grade = grade_patch(tasks / iid, iid, "")
            print(f"{_line(gold_grade)} (gold)")
            print(f"{_line(empty_grade)} (empty)")
            ok = ok and gold_grade.reward == 1 and empty_grade.reward == 0
            grades += [gold_grade, empty_grade]
        out.write_text(json.dumps([g.model_dump() for g in grades], indent=2))
        print("SANITY OK" if ok else "SANITY FAILED")
        raise typer.Exit(0 if ok else 1)

    grades = grade_preds(data, tasks)
    out.write_text(json.dumps([g.model_dump() for g in grades], indent=2))
    for g in grades:
        print(_line(g))
    print(f"resolved {sum(g.reward == 1 for g in grades)}/{len(grades)}")


if __name__ == "__main__":
    app()
