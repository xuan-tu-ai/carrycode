# For researchers

The repository also contains the evaluation harness used to study CarryOn on SWE-bench.

```bash
git clone https://github.com/xuan-tu-ai/carrycode.git
cd carrycode
uv sync
uv run pytest                     # offline tests: no API keys, no Docker
cp .env.example .env              # add the key named in your models config
uv run python scripts/run_swebench.py --help
```

Benchmark runs need Docker. Each experiment is one YAML file in
[`configs/experiments/`](../configs/experiments/), for example the plain baseline, a sliding-window baseline
and CarryOn:

```bash
uv run python scripts/run_swebench.py --experiment configs/experiments/carryon_full.yaml \
  --instances data/m0_instances.txt --workers 2
```

| Path | What is there |
| --- | --- |
| `src/carrycode/` | The runtime: records, registry, view, Tracker, Compiler, Validator, Grounder, agents, CLI |
| `src/carrycode/prompts/` | Tracker and Compiler prompts, written for this project |
| `configs/` | Model and experiment configs |
| `scripts/` | SWE-bench runner, subset selection, result summaries |
| [`docs/paper_map.md`](paper_map.md) | Which paper section each module implements |
| [`docs/decisions.md`](decisions.md) | Design decisions and measurements, newest first |
