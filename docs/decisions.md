# Decision log

Newest first. Add an entry whenever a design choice changes.

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
