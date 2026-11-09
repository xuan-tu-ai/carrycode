<h1 align="center">carrycode</h1>

<p align="center">
  <strong>CarryOn context for coding agents: carry the progress, not the whole history.</strong><br>
  An unofficial, open implementation of <a href="https://arxiv.org/abs/2610.18784"><em>Pack Light, CarryOn</em></a>, wrapped as a coding agent you can run in your own repository.
</p>

<p align="center">
  <a href="https://ethannju.github.io/carryon/"><img src="https://img.shields.io/badge/Project-Page-2d6bb1?style=flat-square" alt="Project Page"></a>
  <a href="https://arxiv.org/abs/2610.18784"><img src="https://img.shields.io/badge/arXiv-2610.18784-b31b1b?style=flat-square" alt="arXiv"></a>
  <a href="https://huggingface.co/papers/2610.18784"><img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fhuggingface.co%2Fapi%2Fpapers%2F2610.18784&amp;query=%24.upvotes&amp;label=Hugging%20Face&amp;prefix=%E2%96%B2%20&amp;suffix=%20upvotes&amp;color=ffd21e&amp;logo=huggingface&amp;style=flat-square" alt="Hugging Face Paper upvotes"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.11%2B-3776ab?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.11+"></a>
  <a href="https://github.com/SWE-agent/mini-swe-agent"><img src="https://img.shields.io/badge/built_on-mini--swe--agent-4b8bbe?style=flat-square" alt="Built on mini-swe-agent"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue?style=flat-square" alt="Apache-2.0"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> · <a href="docs/usage.md">Usage</a> · <a href="docs/how-it-works.md">How it works</a> · <a href="#use-it-in-deepseek-harness">DeepSeek Harness plugin</a> · <a href="#results-reported-in-the-paper">Paper results</a> · <a href="docs/usage.md#troubleshooting">Troubleshooting</a> · <a href="docs/research.md">For researchers</a>
</p>

https://github.com/user-attachments/assets/5f4a6889-5cf6-41a4-aff1-327a9d5d6b7b

<p align="center"><sub>CarryOn demo by the paper's authors. Also on the <a href="https://ethannju.github.io/carryon/">project page</a>.</sub></p>

A coding agent that works for a long time keeps re-reading its own history: every command, every file it opened,
every failed attempt. CarryOn replaces old history with a compact, structured checkpoint of the agent's progress
and keeps only the recent steps verbatim. The context is built from three parts:

- **Continuation carriers**: reusable task objects, such as an edited file, a finding backed by `file:line`
  evidence, or the state of the environment.
- **Execution context**: the goal, constraints and open work that no carrier captures.
- **Live tail**: the raw steps since the last fold.

carrycode puts this runtime under a small, transparent agent ([mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent))
and gives you one command to run it on any repository, with any model that [LiteLLM](https://docs.litellm.ai/docs/providers)
supports.

<p align="center"><img src="https://raw.githubusercontent.com/Ethannju/carryon/2d5c8db78e136a74d6e1cccfdf984607b565ee6e/docs/assets/overview.png" alt="Overview of CarryOn" width="860"></p>
<p align="center"><sub>The CarryOn runtime, from the paper. carrycode implements tracking, compilation and commitment;
its Grounder checks exist but are not yet used inside folds (<a href="docs/how-it-works.md">details</a>).</sub></p>

## Quick start

You need Python 3.11+ and [uv](https://docs.astral.sh/uv/getting-started/installation/). Linux and macOS are
supported; on Windows, use WSL.

```bash
uv tool install git+https://github.com/xuan-tu-ai/carrycode
```

Export the key for your provider (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, ...):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Then run it in your repository:

```bash
cd path/to/your/repo
carrycode run -m anthropic/claude-sonnet-4-6 "Fix the failing test in tests/test_parser.py"
```

The agent proposes one shell command at a time and you approve each one. Each time the runtime folds history into
the checkpoint, you see a line like `carryon: fold 1 committed`.

> [!TIP]
> Commit or stash your work first. The agent edits files in place, and `git diff` then shows exactly what it
> changed. Commands run on your machine with your permissions; see [Safety and privacy](docs/usage.md#safety-and-privacy).

CarryOn helps on **long** sessions. The first fold happens once the live tail reaches about 24,000 tokens, so a short
task behaves exactly like plain mini-swe-agent. Keys, models, options and troubleshooting: [Usage](docs/usage.md).

## Use it in DeepSeek Harness

Prefer a Web UI or a desktop app? [**dsh-carryon**](https://github.com/xuan-tu-ai/dsh-carryon) is a TypeScript port of
carrycode's CarryOn runtime as a compaction plugin for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)
(dsh), [published on npm](https://www.npmjs.com/package/dsh-carryon). It folds long dsh sessions with the same
Tracker, Compiler and Validator, checked against carrycode's parity fixtures, and adds a CarryOn mode to dsh's Web UI:

```bash
npx @deepseek-ai/dsh@0.2.2-alpha.3 plugin --profile web add dsh-carryon
```

## Results reported in the paper

These results come from the paper (Lu, McAuley, Zhang, 2026), with Claude Opus 4.7 as the agent. carrycode has not
been benchmarked against them.

<p align="center"><img src="https://raw.githubusercontent.com/Ethannju/carryon/2d5c8db78e136a74d6e1cccfdf984607b565ee6e/docs/assets/osworld-results.png" alt="Task performance on OSWorld 2.0" width="760"></p>
<p align="center"><sub>OSWorld 2.0. CarryOn improves both binary and partial scores of the same Claude Opus 4.7 agent
while cutting cost per task by 35.9%. Figure from the paper's authors.</sub></p>

<p align="center"><img src="https://raw.githubusercontent.com/Ethannju/carryon/2d5c8db78e136a74d6e1cccfdf984607b565ee6e/docs/assets/context-and-cost.png" alt="Context and cost over agent turns on OSWorld 2.0" width="760"></p>
<p align="center"><sub>Context and cost over agent turns on OSWorld 2.0. The baseline's input context keeps growing past
200K tokens, while CarryOn's stays near 65K. Figure from the paper's authors.</sub></p>

On BrowseComp-Plus, the paper reports accuracy rising from 49.0% to 56.0% with 22.9% fewer tokens per task.

## Documentation

| Page | What is there |
| --- | --- |
| [Usage](docs/usage.md) | Working with the agent, choosing models, all options, safety, troubleshooting |
| [How it works](docs/how-it-works.md) | Folds, the Tracker, Compiler and Validator, and what carrycode adds to the paper |
| [For researchers](docs/research.md) | The SWE-bench evaluation harness and the repository layout |

## Acknowledgements

- Yuchen Lu, Julian McAuley and Lei Zhang, for the CarryOn paper, and for permission to show their demo and figures
  here.
- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent), the agent loop carrycode extends.
- [LiteLLM](https://github.com/BerriAI/litellm), for one interface to every model provider.

## Citation

If you use carrycode, please cite the original paper:

```bibtex
@article{lu2026carryon,
  title   = {Pack Light, CarryOn: Building Object-Oriented Context for Long-Horizon Agents},
  author  = {Lu, Yuchen and McAuley, Julian and Zhang, Lei},
  journal = {arXiv preprint arXiv:2610.18784},
  year    = {2026}
}
```

carrycode is an independent reimplementation built from the paper. It is not affiliated with the paper's authors;
their official code is announced on the [project page](https://ethannju.github.io/carryon/).

## License

carrycode's code is Apache-2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). The demo video and the figures shown
above belong to the paper's authors and are not covered by that license.
