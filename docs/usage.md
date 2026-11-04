# Using carrycode

Install and first run: see the [README](../README.md#quick-start).

## Working with the agent

carrycode uses mini-swe-agent's terminal loop. By default it runs in **confirm** mode:

| You type | Effect |
| --- | --- |
| <kbd>Enter</kbd> | Run the proposed command |
| any text | Reject the command and send your text to the agent as feedback |
| `/y` | Switch to **yolo** mode: run commands without asking |
| `/c` | Switch back to **confirm** mode |
| `/u` | Switch to **human** mode: you type the commands yourself |
| `/h` | Show help |
| <kbd>Ctrl</kbd>+<kbd>C</kbd> | Interrupt the agent and give it a comment |

When the agent says it is done, type a follow-up task or press <kbd>Enter</kbd> to quit. Each time the
runtime folds history into the checkpoint, you will see a line like:

```text
carryon: fold 1 committed; the live tail now starts at message 14.
```

At the end, carrycode prints the exit status, steps, cost and number of folds, and saves the full
trajectory (every message, plus the carriers and fold events) to the file given by `--output`.

## Choosing models

Pass any LiteLLM model id with `-m`. The agent model must support **tool calling**; the runtime model
must return **JSON**. A few examples:

| Provider | Key variable | Example `-m` |
| --- | --- | --- |
| Anthropic | `ANTHROPIC_API_KEY` | `anthropic/claude-sonnet-4-6`, `anthropic/claude-opus-4-6` |
| OpenAI | `OPENAI_API_KEY` | `openai/gpt-5` |
| Google Gemini | `GEMINI_API_KEY` | `gemini/gemini-2.5-pro` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek/deepseek-chat` |

See the [LiteLLM provider list](https://docs.litellm.ai/docs/providers) for the rest.

**Save money with a cheaper runtime model.** The Tracker and Compiler only read and summarise, so a smaller
model usually does:

```bash
carrycode run -m anthropic/claude-opus-4-6 --runtime-model anthropic/claude-sonnet-4-6 "..."
```

**OpenAI-compatible endpoints and custom settings.** Put the models in a YAML file and pass `--models`.
The files in [`configs/models/`](../configs/models/) are working examples (an OpenAI-compatible gateway with
its own key variable, extra `model_kwargs`, prices for models LiteLLM does not know):

```yaml
# my-models.yaml
api_key_env: MY_GATEWAY_KEY          # copied to OPENAI_API_KEY at startup
host:
  model_name: "openai/my-model"
  model_kwargs: { api_base: "https://gateway.example.com/v1", drop_params: true }
runtime:
  model_name: "openai/my-model"
  model_kwargs: { api_base: "https://gateway.example.com/v1", drop_params: true }
```

```bash
carrycode run --models my-models.yaml "..."
```

## Options

```text
carrycode run [TASK] [OPTIONS]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `-m, --model` | (required) | LiteLLM model id for the agent |
| `--runtime-model` | same as `--model` | Model for the Tracker and the Compiler |
| `--models FILE` | | Models YAML; replaces `--model` and `--runtime-model` |
| `--cwd DIR` | `.` | Repository to work in |
| `-y, --yolo` | off | Run commands without asking |
| `-l, --cost-limit` | `3` | Stop after this many dollars; `0` disables the limit |
| `--step-limit` | `0` (none) | Stop after this many model calls |
| `--trigger-tokens` | `24000` | Fold when the live tail reaches this many tokens |
| `--keep-recent-tokens` | `8000` | Raw recent history kept after a fold |
| `-o, --output` | `<mini-swe-agent config dir>/last_carrycode_run.traj.json` | Where to save the trajectory |
| `--exit-immediately` | off | Quit when the agent finishes instead of asking for a new task |

When a limit is reached in an interactive terminal, you are asked for new limits instead of the run
stopping.

## Safety and privacy

- Commands run **on your machine with your permissions**. Keep confirm mode on unless the repository is
  disposable or you run carrycode inside a container or VM.
- Your code and command output are sent to the model provider you choose, as with any coding agent.
- API keys are read from the environment and never written to trajectory files.

## Troubleshooting

<details>
<summary><b>"Missing credentials" or an authentication error</b></summary>

The key variable for your provider is not set in this shell. Run `export ANTHROPIC_API_KEY=...` (or the
variable for your provider) and try again. With `--models`, the file's `api_key_env` names the variable.
</details>

<details>
<summary><b>"Error calculating cost for model ..."</b></summary>

LiteLLM has no price for the model, so the cost limit cannot be enforced. Either add prices with a models
file (`price_registry`, see [`configs/models/litellm_registry.json`](../configs/models/litellm_registry.json)),
or skip cost tracking:

```bash
export MSWEA_COST_TRACKING=ignore_errors
```
</details>

<details>
<summary><b>The model replies but never runs a command</b></summary>

The agent model must support tool calling. Pick a model with function or tool calling in LiteLLM's
provider docs.
</details>

<details>
<summary><b>No fold ever happens</b></summary>

That is expected on short tasks: the live tail never reaches `--trigger-tokens` (24,000 by default). Lower
it, for example `--trigger-tokens 8000 --keep-recent-tokens 2000`, to see folds sooner.
</details>

<details>
<summary><b>"Warning: Input is not a terminal"</b></summary>

Harmless. It appears when stdin is not a terminal, for example in scripts. Use `--yolo --exit-immediately`
for unattended runs.
</details>
