# Decision log

Newest first. Add an entry whenever a design choice changes.

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
