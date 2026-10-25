# Decision log

Newest first. Add an entry whenever a design choice changes.

## 2026-10-25: First CarryOn measurement on SWE-bench Pro (GPT-6 Luna, 3 pilot tasks)

- Setup: `pilot_luna` (baseline) vs `pilot_luna_carryon` (CarryOn, trigger 6000, Luna for all roles), same 3 pilot
  tasks, `step_limit: 150`, agent containers offline, graded with the local V2 verifier (sanity: gold 1, empty 0).
- Resolved: baseline 3/3, CarryOn 3/3.
- Cost: CarryOn used **2.3× the tokens** (3.58M vs 1.59M) and 3.2× the nominal cost ($0.51 vs $0.16); runtime roles
  were 30% of CarryOn's tokens. Steps: 188 vs 57 (ansible 48 vs 21, openlibrary 114 vs 22, qutebrowser 26 vs 14).
- Folding itself worked: 29/53 folds committed (22 "no compile request", 1 abstain, 1 unauthorized citation), no
  crash, prompts reset to ~2k tokens after each commit, max prompt 22.9k/36.6k/29.4k vs 38.8k/54.6k/31.4k.
- Cause of the extra steps: re-reading. After a fold the live tail is empty and carriers hold summaries, not code,
  so the agent reads the files again: `parse.py` 91 reads vs 15, `module_common.py` 42 vs 16 (re-reads per file
  19.3 vs 3.3 and 17.7 vs 5.2).
- Conclusion: with the paper's OSWorld settings, CarryOn does not pay off for coding; it fragments the working set.
  Next (M2): keep a recent part of the tail after a fold, fold less often (higher trigger), and test again.

## 2026-10-25: Grade SWE-bench Pro V2 locally; agent phase offline

- `ScaleAI/SWE-bench_Pro` (default config) is **V2**, graded by per-task verifiers in the evaluator repo
  (`v2/tasks/<id>/tests/test.sh`, normally run with Harbor on Modal). The repo's root `swe_bench_pro_eval.py` is the
  v1 evaluator with different images; we do not use it, and `to_pro_patches` (T024) is no longer needed.
- Local grading: fresh task image, copy `tests/` to `/tests`, `git apply` the patch in `/app`, run `test.sh`, read
  `/logs/verifier/reward.txt` (T026, `scripts/grade_pro.py`). Checked on the openlibrary pilot task: reference patch 1,
  empty patch 0, GPT-6 Luna's baseline patch 1 (59/59 required tests; 23 steps, ~706k tokens).
- This machine's Docker is a snap and cannot read host `/tmp`: bind mounts and `docker cp` fail silently. The grader
  sends files through stdin.
- Agent containers for Pro run with `--network none`, as in the official locked protocol, so scores are comparable.
  Model calls come from the host process and are unaffected. The grader's containers keep network.
- All 237 Python Pro images use `/app` (the "/testbed in a few tasks" note does not apply to our subset).

## 2026-10-25: GPT-6 Luna via the ChatGPT subscription while Token Harbor is out of allowance

- The Agent Pass allowance is used up (HTTP 402 on every model). The T025 pilot is paused until it returns.
- Stopgap: `configs/models/luna.yaml`, LiteLLM's `chatgpt/` provider (ChatGPT/Codex subscription), GPT-6 Luna for
  host, Tracker and Compiler, `reasoning_effort: max` (applied: `low` gives 0 reasoning tokens, `max` the most).
- Sign-in: LiteLLM device login; tokens in `~/.config/litellm/chatgpt/auth.json` (mode 600), separate from Codex/omp.
- Two traps, both handled in config: LiteLLM prepends a ~7.6 KB "You are Codex" prompt unless
  `CHATGPT_DEFAULT_INSTRUCTIONS` is set (new `ModelsConfig.env`, applied by `setup_provider`); and the price entry
  needs `"mode": "responses"`, otherwise tool calls go to a nonexistent `/backend-api/codex/chat/completions`.
- Costs are nominal (Token Harbor's gpt-6-luna rates) so `cost_limit` works; the subscription is not billed per token.
- Checked live on the toy repo: baseline Submitted in 6 steps; carryon_full 1/2 folds committed, no orphaned tool
  messages, tests pass; no token in saved trajectories.
- Token Harbor's `openai/gpt-6-luna` would also use the Responses API (LiteLLM knows the model); Token Harbor serves
  `/v1/responses`, but tool calls through it are untested.

## 2026-10-23: Evaluate on SWE-bench Pro (Python subset); pilot four cheap hosts

- Why: on SWE-bench Verified, mini-swe-agent trajectories stay short (our runs: 4–9 steps, 1–3k tail tokens;
  SambaNova reports conversations "generally under 20k tokens"), so CarryOn never folds. The paper's gains come
  from 500-step OSWorld 2.0 runs whose context exceeds 200K tokens.
- Benchmark: `ScaleAI/SWE-bench_Pro` public set (642 tasks; MIT-licensed harness at scaleapi/SWE-bench_Pro-os).
  M3 uses only the 237 Python tasks (ansible, openlibrary, qutebrowser): the Grounder checks are Python-only
  until M2 ends. Images: `ghcr.io/scaleapi/swe-bench_pro-v2:<id>` (dataset column `docker_image`), workdir `/app`.
  Task text = problem statement + requirements + interface, as in the official setup.
- Models: Agent Pass only covers cheap models (Sonnet/Opus/Kimi K3/GPT-6 Sol are refused). Pilot hosts, all with
  `reasoning_effort: max` (accepted by every one; Token Harbor does not report reasoning tokens, so its effect
  is unverified): GPT-6 Luna ($0.10/$0.50), MiniMax M3.1 Flash ($0.15/$0.60), DeepSeek V4.1 Flash 1017
  ($0.30/$1.20), Haiku 5.5 as control ($0.10/$0.50; **$0.50/$2.50 for prompts over 100k tokens**, which our
  price registry does not model yet). The pilot winner runs host, Tracker and Compiler (one model, as in the paper).
- Budget: under $50 total. Pilot: 4 hosts × 3 tasks, `step_limit: 150`, `cost_limit: 1.5` (≤ $18). M3 size is set
  after the pilot from the measured cost per task.
- SWE-bench Verified support stays (`benchmark: verified` is the default).

## 2026-10-23: M1 first real CarryOn run

- 3 instances, carryon_full (no Grounder yet): 3/3 resolved (baseline: 3/3). **No fold was attempted**: these tasks
  end with live tails of 1.2k–3.2k estimated tokens, below `trigger_tokens: 6000`, so the run was the baseline in
  a CarryOnAgent wrapper. Mean per task 24,724 tokens, $0.0033 (baseline 26,594 tokens, $0.0032; run-to-run noise).
- Smoke rerun with `trigger_tokens: 1000` (`runs/carryon_smoke/`, ad hoc config): 3/3 resolved; 4 folds attempted,
  0 committed. Rejections: "no compile request" (astropy, 2×: the Tracker found nothing worth compiling) and
  "claim cites unauthorized steps [5]" (sympy, 2×: the Compiler cited a tail step that was not in `# Evidence`).
  Mean 46,723 tokens (runtime share 31%), $0.0063: twice the baseline, with nothing retired.
- Conclusion: M1 shows the pipeline runs on real tasks without crashing; it does not yet show any benefit. The
  benefit can only appear on long trajectories (M3 picks the longest baseline runs).
- Follow-up for M2: stop whole-fold rejection for one bad citation (drop or repair the claim, or add the cited
  tail steps to the evidence), then retest on a long task.

## 2026-10-23: M0 baseline numbers

- 3 instances (data/m0_instances.txt), baseline config, Claude Haiku 5.5: 3/3 resolved
  (official harness, dataset `SWE-bench/SWE-bench_Verified`; swebench 5.x needs that copy, not `princeton-nlp/...`).
- Mean per task: 5.3 calls, 26,594 tokens, $0.0032.
- Budget estimate for M3 (4 configs × 30 tasks, ~1.3× for runtime overhead): about $0.50. These 3 tasks are easy
  (4–7 steps); harder tasks can use 10–50× more, so plan for $5–25 and rely on `cost_limit` per task.

## 2026-10-23: Claude Haiku 5.5 via Token Harbor (Agent Pass)

- Plan: Token Harbor Agent Pass ($1.99/month, $10 included usage). Same endpoint and key variable
  (`TOKENHARBOR_API_KEY`).
- Model: `claude-haiku-5.5` for host and runtime (`configs/models/haiku.yaml`; all experiments point to it).
  $0.10/M input, $0.50/M output, 1M context. `deepseek.yaml` stays as an alternative.
- Live check: plain, bash tool call and JSON mode succeed. Haiku wraps JSON-mode replies in a ```json fence,
  so `RoleLLM` now strips one surrounding code fence before parsing.
- Request `timeout: 120` on host and runtime calls (a stalled provider otherwise blocks up to 600 s per call).
- Price update: paid `deepseek-v4.1-flash` is now $0.30/M input, $1.20/M output.

## 2026-10-22: Runtime prompts are language-neutral; Grounder checks stay Python for now

- Tracker and Compiler prompts must not assume Python: carriers (files, findings, state) work for any stack,
  e.g. a React site. Language-specific checks are labelled ("Python only").
- The Grounder keeps `python_compiles` / `test_outcome` (pytest) through M3, since SWE-bench Verified is all
  Python. M2 adds a generic `command_exit` check (any build/test command + expected exit code) and fixes
  `git_diff_nonempty` for new (untracked) files.

## 2026-10-22: Compiler proposes CarrierEdits; runtime assigns versions

- The Compiler returns `CarrierEdit`s (no version or fold fields). The runtime derives carrier ids from
  type + normalized subject and assigns versions in `CarrierStore.materialize`.
- Updates carry `base_version`; the validator rejects stale bases (compare-and-swap, paper §3.3).
- Why: LLMs get bookkeeping fields wrong, which would turn into avoidable rejected folds.

## 2026-10-21: DeepSeek V4.1 Flash via Token Harbor

- Provider: Token Harbor, OpenAI-compatible (`https://tokenharbor.ai/v1`); LiteLLM id `openai/<model>`.
  Key in `TOKENHARBOR_API_KEY`, copied to `OPENAI_API_KEY` at startup so it never enters trajectories.
- Model: `deepseek-v4.1-flash:free` for host and runtime while the account balance is $0. Paid
  `deepseek-v4.1-flash` is $0.15/M input, $0.60/M output, $0.03/M cache read, 1M context, tool calls.
- Costs are tracked at the paid rates (`configs/models/litellm_registry.json`) so `cost_limit` works and
  budgets are realistic; reported costs for `:free` runs are nominal, not billed.
- Pinned `litellm<1.106`: 1.106.0 (2026-10-18) imports the optional `mcp` package on every request with
  `tools`, which breaks mini-swe-agent's tool calls.
- Checked: plain, tool-call and JSON-mode requests succeed; Docker runs without sudo.

## 2026-10-19: initial setup

- **Goal:** public harness for coding agents, not a paper reproduction. Solo project, a few hours
  per week, API budget under $200.
- **Host agent:** mini-swe-agent, installed as a dependency and extended by subclassing.
- **Models:** DeepSeek for both the host agent and the runtime roles (Tracker, Compiler).
  Chosen over Gemini free tier (daily caps) and local models (simpler setup).
  Only public/open-source code is sent to the API.
- **Evaluation:** 20–30 SWE-bench Verified tasks with the longest baseline trajectories.
  Configs: baseline, sliding window, CarryOn, CarryOn without code checks.
- **Environment:** Linux with Docker; Python via uv.
- **License:** Apache-2.0. No code or prompt text from the original authors (their repo has
  no license and no code as of 2026-10-19).
