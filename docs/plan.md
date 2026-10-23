# Plan

Full plan (architecture, evaluation, risks):
https://claude.ai/code/artifact/86d9e097-bfad-43f4-85b2-27b9369acc9c

Model choices changed after that plan was written; `decisions.md` is authoritative.

## Milestones

| Milestone | Weeks (estimate) | Done when |
| --- | --- | --- |
| M0 Setup | 1–2 | Plain mini-swe-agent + DeepSeek runs 3 SWE-bench Verified tasks via `scripts/run_swebench.py` |
| M1 Fold skeleton | 3–5 | Tracker and Compiler produce valid JSON; a fold commits without breaking the message log |
| M2 Carriers + Grounder | 6–9 | Validator complete; coding checks used in folds; offline tests pass |
| M3 Evaluation | 10–12 | Results for all four configs in `configs/experiments/` |
| M4 Release | 13–14 | README with results, short report, issue opened on the original CarryOn repo |

## M0 checklist

- [x] `uv sync`, `uv run pytest` pass
- [x] Docker works without sudo
- [x] Confirm DeepSeek model id and price in `configs/models/deepseek.yaml`
- [ ] Implement `scripts/run_swebench.py` for the `baseline` config
- [ ] Run 3 instances; run the official SWE-bench harness on `preds.json`
- [ ] Record tokens and cost per task; update the budget estimate

## M1 checklist

- [x] Tracker and Compiler prompts (own wording, not Appendix D)
- [x] `Tracker.scan`, `Compiler.compile`, `CarryOnRuntime.fold` with atomic commit
- [x] Runtime state saved in trajectories (`info.carryon`)
- [x] Offline end-to-end fold test (`tests/test_fold_e2e.py`)
- [ ] Real `carryon_full` run on the 3 M0 instances (T020)
