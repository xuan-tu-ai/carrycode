---
name: verify
description: How to verify carrycode changes at runtime (real agent + real model on a toy repo), not via unit tests.
---

# Verifying carrycode

Surface = the agent. Runtime roles (Tracker, Compiler, fold) have no CLI of their own; drive them through a real
`CarryOnAgent` run, or the role directly with a real `RoleLLM`, against a live model.

## Setup
- Key: `.env` must contain `TOKENHARBOR_API_KEY` (check the exact name; it has been mistyped before).
- Model config: `configs/models/haiku.yaml` (Claude Haiku 5.5 via Token Harbor). Call `setup_provider(models)`
  after `dotenv.load_dotenv(REPO_ROOT / ".env")`.
- Docker group: shells started before `usermod -aG docker` need `sg docker -c "..."`.

## Recipe: full fold on a toy repo (about 1 minute, under 1 cent)
1. `mktemp -d`; make a git repo with a small buggy package (e.g. `calc.mean` divides by `len-1`) and a pytest file.
2. Build the runtime with `factory.build_runtime(exp, models)` (Tracker and Compiler on `models.runtime`), with
   `trigger_tokens=800` for the toy repo.
3. Host: `get_model(config=build_mswea_config(exp, models)["model"])`; wrap `host.query` to record each view.
4. `CarryOnAgent(host, LocalEnvironment(cwd=repo), runtime=rt, **agent_cfg)`; replace `/testbed` in
   `instance_template` with the repo path; `step_limit` about 20.
5. Check: `rt.events` (committed/rejected + reason), `rt.store.current()`, views containing `<carryon_checkpoint>`,
   no orphan `tool` messages in any view, `views[k][3:] == agent.messages[fold_index:...]` (log append-only),
   and that the repo's tests pass afterwards (`.venv/bin/python -m pytest -q -p no:cacheprovider`).

## Probes worth running
- Compiler on a nonexistent model id (`openai/no-such-model-xyz`): the fold must be rejected, the agent must continue
  and submit.
- Role-only runs on a hand-made tail (React/TS tool-call messages) for prompt behaviour; cut the tail before a command's
  output to test the "unobserved result" rule.

## Gotchas
- Free tiers stall or rate-limit (Token Harbor `:free` hung for 90 s; Gemini free is 5 requests/min). Use the paid model.
- The LiteLLM "custom pricing ... cache cost will default to 0" warning is harmless.
