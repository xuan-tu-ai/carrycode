# carrycode

**Status: work in progress (milestone M0). Nothing here is benchmarked yet.**

carrycode is an open, independent reimplementation of the context runtime described in
[*Pack Light, CarryOn: Building Object-Oriented Context for Long-Horizon Agents*](https://arxiv.org/abs/2610.18784)
(Lu, McAuley, Zhang, 2026), adapted to **coding agents**.

The original authors have not released their code yet. carrycode is built from the paper alone
and is not affiliated with them.

## Idea in one paragraph

A long-horizon agent keeps re-reading the history of *how* it made progress, even though the
progress already lives in the environment (edited files, test results, findings). CarryOn replaces
old history with a **context view** of three parts:

- **continuation carriers**: reusable task objects and their conditions of use;
- **execution context**: goals, constraints and open work not captured by carriers;
- **live tail**: the raw interactions since the last fold.

## What carrycode adds

1. **Coding domain.** Carriers are edited files, findings with `file:line` evidence, environment
   state and test results.
2. **A content-level Grounder.** Before a carrier is committed, it is checked by running the
   recorded tests, `git diff`, and compilation inside the task's Docker container. The paper's
   OSWorld checks only look at file existence, hashes and document structure.
3. **Low-cost setup.** Host agent and runtime both run on DeepSeek V4.1 Flash (via Token Harbor); a full evaluation targets
   under $200 of API spend.

## Layout

```
src/carrycode/       the runtime: records, registry, view, tracker, grounder, compiler, validator
configs/             model and experiment configs (YAML)
scripts/             SWE-bench runner, subset selection, result summaries
tests/               offline unit tests (no API, no Docker)
docs/                design notes, paper-to-code map, decision log
data/                SWE-bench Verified instance IDs used in the evaluation
```

## Quick start

Requires Linux, Docker, Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/xuan-tu-ai/carrycode.git
cd carrycode
uv sync
cp .env.example .env        # add TOKENHARBOR_API_KEY
uv run pytest               # offline tests
```

The SWE-bench runner (`scripts/run_swebench.py`) is not implemented yet; see `docs/plan.md`.

## Citation

If you use this code, please cite the original paper:

```bibtex
@article{lu2026carryon,
  title   = {Pack Light, CarryOn: Building Object-Oriented Context for Long-Horizon Agents},
  author  = {Lu, Yuchen and McAuley, Julian and Zhang, Lei},
  journal = {arXiv preprint arXiv:2610.18784},
  year    = {2026}
}
```

## License

Apache-2.0. See `LICENSE` and `NOTICE`.
