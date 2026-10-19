# Decision log

Newest first. Add an entry whenever a design choice changes.

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
