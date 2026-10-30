# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this project is

carrycode reimplements and improves the CarryOn context runtime (arXiv:2610.18784) for coding agents, on top of
mini-swe-agent, and evaluates it on 20–30 SWE-bench Verified tasks.

## Hard rules

- **Never copy prompt text from the paper's Appendix D.** The original repo has no license.
  Write our own prompts in `src/carrycode/prompts/`, guided by the paper's ideas.
- **mini-swe-agent is an installed dependency, not a fork.** Extend it by subclassing
  (`DefaultAgent`). Do not vendor or patch its source.
- **`agent.messages` is the append-only interaction log.** Never delete or rewrite it. Only the
  list sent to the model (the context view) changes after a fold.
- **The live tail must start on a valid message boundary.** mini-swe-agent uses tool calls: an
  assistant message with `tool_calls` and its tool-result messages must stay together. Use
  `carrycode.view.safe_tail_start`.
- **The Grounder is read-only.** It may run tests and git commands, but must leave the repo
  unchanged (`git status --porcelain` identical before and after). Use
  `PYTHONDONTWRITEBYTECODE=1` and `pytest -p no:cacheprovider`.
- **A fold must change at least one carrier.** Updating only the execution context does not
  retire history (paper §3.3).
- **A failed fold changes nothing.** Committed carriers, execution context and live tail stay
  as they were.
- Unit tests must run offline: no API keys, no Docker. Mock the LLM and the environment.

## Commands

```bash
uv sync                      # install
uv run pytest                # tests
uv run ruff check . && uv run ruff format .
uv run python scripts/run_swebench.py --help
uv run carrycode run --help                    # local CLI
```

## Layout

- `src/carrycode/records.py`: pydantic data models (Candidate, CarrierRecord, Claim, ExecutionContext)
- `src/carrycode/registry.py`: candidate registry and versioned carrier store
- `src/carrycode/view.py`: builds the context view; live-tail boundary helper
- `src/carrycode/agent.py`: `CarryOnAgent` and `SlidingWindowAgent` (subclasses of `DefaultAgent`)
- `src/carrycode/cli.py`: `carrycode run`, the CarryOn agent in a local repo (`InteractiveCarryOnAgent`)
- `src/carrycode/runtime.py`: fold orchestration (trigger → Tracker → Grounder → Compiler → Validator → commit)
- `src/carrycode/tracker.py`, `compiler.py`, `validator.py`: runtime roles
- `src/carrycode/grounder/`: verdict rules (`base.py`) and coding checks (files, git, tests)
- `src/carrycode/llm.py`: JSON-output LLM calls for runtime roles, via LiteLLM
- `configs/models/`: one YAML per model; `configs/experiments/`: one YAML per evaluated configuration
- `scripts/`: SWE-bench runner, subset selection, summaries
- `docs/decisions.md`: decision log. Add an entry when a design choice changes.

## Current milestone

M0 done (baseline 3/3 resolved, Haiku 5.5). M1: fold skeleton done offline; real run pending (docs/tasks/T020).
Next: M2 (Grounder checks in folds). See `docs/plan.md`.

## Style

Python 3.11+, type hints everywhere, pydantic v2 models, small functions, docstrings that cite
the paper section they implement (e.g. `Implements §3.3, "Validation and Commitment"`).
