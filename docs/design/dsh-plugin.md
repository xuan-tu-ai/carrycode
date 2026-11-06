# Design: CarryOn as a DeepSeek Harness compaction plugin (`dsh-carryon`)

Status: implemented in [xuan-tu-ai/dsh-carryon](https://github.com/xuan-tu-ai/dsh-carryon); 0.1.0 released on npm
on 2026-11-06 for dsh `0.2.2-alpha.3`. This document is the original proposal. Owner: carrycode maintainers. Last checked against DeepSeek Harness (dsh)
`main` at `ce7073d5` (2026-10-30, CLI `0.2.2-alpha.2`).

## 1. Goal

`carrycode run` only has a terminal interface. DeepSeek Harness ([deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness),
MIT) already has a Web UI (`npx @deepseek-ai/dsh web`), a desktop app, a plugin installer and a replaceable
compaction service. We want users to get CarryOn folding inside dsh, with the dsh UI, by installing one
plugin.

Non-goals: replacing carrycode's Python runtime (it stays the reference and the SWE-bench harness); changing
dsh itself; claiming benchmark results for the plugin.

## 2. Decisions

| Question | Decision | Why |
| --- | --- | --- |
| Fork dsh or write a plugin? | **Plugin**, installed with `dsh plugin add` | Compaction is a replaceable service (`ctx.compaction`); a fork of a developer-preview project would need constant rebasing. |
| Language | **Port the runtime to TypeScript** | Plain npm install, one process, model calls through dsh's `ctx.llm` (shared credentials, provider routing and cost accounting). |
| Where | **Separate repository** `dsh-carryon` (GitHub topic `dsh-plugin`) | Different toolchain (pnpm, TS) and release cycle from carrycode. |

Alternatives considered and rejected:

- **Python plugin through the dsh Python SDK.** Not possible: `python/sdk` is a JSON-RPC client that starts
  `dsh` as a subprocess. It can send prompts and commands (including `/compact`), answer
  `on_user_question` and approval requests, and install bundles, but plugins (including compaction backends)
  are JavaScript Cordis packages. There is no Python hook for `ctx.compaction`.
- **Thin TS plugin + Python sidecar** (TS subclass calls carrycode's Python runtime through `ctx.subprocess`).
  Per-fold overhead is negligible next to the two model calls, but users would need Python/uv next to dsh,
  and model calls would bypass `ctx.llm` unless routed back over RPC. Rejected in favour of a single-language
  install; see the decision log entry of 2026-11-03.

## 3. The dsh compaction contract (what we plug into)

Facts verified in `packages/compaction/*`:

- `CompactionEngine` (`@deepseek-ai/dsh-compaction`) is an abstract Cordis `Service` registered as
  `ctx.compaction`, with `compactIfNeeded(agent, trigger, signal)`, `compactNow(agent, signal, cmdId?)` and
  `compactRegion(start, end, agent, signal?)`. One implementation per context.
- The shipped backend `BasicCompactionEngine` (`@deepseek-ai/dsh-compaction-basic`) owns pressure policy,
  retention of a verbatim tail, the lock bracket, tool-pair-safe edges, shrink validation and shadowed-token
  accounting. Its README states that **`summarize(input, agent, signal)` is the sole subclass hook**, meant
  for "template or remote" summarizers.
- `summarize()` receives `SummarizationInput { tools?, messages }`: the derived system head followed by the
  region to be shadowed, in surface order. It returns `SummaryResult { summary: ContentBlock[], provider, model,
  maxTokens?, usage?, rawOutput? }`. The *unmarked* variant (no `llmStreamCall: true`) is allowed for
  summarizers that do not make exactly one `ctx.llm.stream()` call, which is our case (Tracker + Compiler).
- A successful run appends `compaction/start` → `compaction/summary` (log-only) → one replacement
  `user/message` (the only surface change) → `compaction/end`. Shadowed events stay in the log; replay is
  deterministic. A failure leaves the surface unchanged and records `compaction/end` with `error`.
- Edge helpers `toolPairingBalancedBefore/After(session, seq)` keep tool calls and results together.
- Config of the basic backend: `thresholdRatio` (default 0.8 of the window), `headroomTokens`, `retainRatio`
  (default 0.16) / `retainTokens`, `summarizationProvider`/`summarizationModel`, `maxTokens`,
  `compactionRetries` (default 1), `maxOverflowRetries`, `modelPolicies`, `auto`.
- Plugins ship as a **bundle**: an npm package whose `package.json` declares `dsh.bundle.patch` and
  `engines.dsh`, with a `cordis.patch.yml` layer. The `dsh-base` bundle mounts the backend as row
  `id: compaction-basic`.

How this lines up with carrycode's hard rules (CLAUDE.md):

| carrycode rule | dsh mechanism |
| --- | --- |
| `agent.messages` is append-only; only the view changes | Shadowed events stay in the log; the surface gets one replacement node |
| Live tail starts on a valid boundary (`safe_tail_start`) | Basic backend snaps edges with the tool-pairing helpers |
| A failed fold changes nothing | `summarize()` throws → no replacement, `compaction/end{error}` |
| Checkpoint rendered as one user message | Replacement `user/message` with `compactCheckpointSource` |
| Partial fold, `keep_recent_tokens` | `retainTokens` (verbatim tail kept by the basic backend) |

## 4. Architecture

```
dsh agent loop ──pressure──▶ CarryOnCompactionEngine (extends BasicCompactionEngine)
                               │  inherited: trigger, retention, lock, edges, shrink check, accounting
                               └─ summarize(input, agent, signal)          ◀── our code
                                    1. load CarryOnState from the session log (last fold)
                                    2. project input.messages → numbered step text
                                    3. Tracker  (ctx.llm.stream, JSON)  → candidate updates, compile requests
                                    4. Compiler (ctx.llm.stream, JSON)  → carrier edits, execution context
                                    5. Validator → problems? throw (fold fails, nothing changes)
                                    6. materialize + apply to the carrier store (in memory copy)
                                    7. return { summary: [renderCheckpoint()], rawOutput: [state], usage, … }
```

### 4.1 State across folds (main design risk)

The Python runtime keeps `CarrierStore`, `CandidateRegistry` and `ExecutionContext` in memory. In dsh a
session can be resumed, forked or replayed in another process, so the state must be durable and must come
from the log, not from plugin memory.

Options checked:

1. **`compaction/summary.rawOutput`** (chosen for v1). Log-only, part of the core event schema, carried by
   resume and fork, readable after the plugin is uninstalled. We store one text block
   `{"carryon_state": {"v": 1, "task": …, "carriers": […], "registry": […], "ec": {…}}}`. On each fold we read
   the latest `compaction/summary` of the session and parse it if present. Risk: `rawOutput` is meant as "the
   complete output of the summarizer"; storing state there stretches that meaning. We must check whether the
   Web UI displays `rawOutput`.
2. Own `SessionEventMap` events (declaration merging is allowed for plugins; such events are log-only). Not
   chosen: persistence of non-core event types from an external package, and what happens to old sessions
   once the plugin is removed, are not documented for out-of-tree plugins.
3. `appendPluginRecord()` / `plugin:*` records. **Not allowed**: the session README restricts callers to
   `packages/experimental/` and says out-of-tree plugins must not call it.

Consequence: candidate-registry updates from a *failed* fold are kept only in process memory (the Python
runtime keeps them too, App. A.1), and are lost on resume. Acceptable for v1.

### 4.2 Task text

The Tracker and Compiler need the original task. On the first fold it is the first user message in
`input.messages`; we store it in `CarryOnState.task` so later folds, whose region starts at the previous
checkpoint, still have it.

### 4.3 Trigger policy

carrycode v2 folds when the live tail has grown by 24k tokens since the last scan; dsh folds at 80% of the
context window with a verbatim tail. v1 keeps dsh's pressure trigger (configure `thresholdRatio`,
`retainTokens`), so folds happen less often and each covers more history. This is a behaviour change from the
measured carrycode configuration and must be stated in the plugin README. An absolute-token trigger
(override `compactIfNeeded`, call `compactRegion` on a tool-balanced range) is a v2 option once v1 works.

`compactionRetries` should default to 0 for this backend: a retry re-runs both roles and costs as much as a
fold; a Validator rejection is usually not fixed by retrying the same input.

### 4.4 Model calls

Tracker and Compiler call `ctx.llm.stream()` with the abort signal forwarded (required by the contract).
Model: plugin config `runtimeProvider`/`runtimeModel`, defaulting to the agent's routed model, as
`carrycode run` does. `usage` in `SummaryResult` is the sum of both calls; `provider`/`model` are the
Compiler's. JSON extraction and the retry-on-invalid-JSON logic port from `src/carrycode/llm.py`.

### 4.5 Checkpoint text

`summary` is one text block rendered exactly like `carrycode.view.render_checkpoint`
(`<carryon_checkpoint>` … `</carryon_checkpoint>`). The basic backend's shrink validation requires it to be
smaller than the shadowed region; a fold that does not shrink fails and changes nothing.

### 4.6 Grounder

Not used in folds yet (carrycode M2). When it is, checks run through dsh's shell/sandbox seams under the
same read-only rule (`git status --porcelain` unchanged, `PYTHONDONTWRITEBYTECODE=1`,
`pytest -p no:cacheprovider`). Out of scope for v1.

## 5. Port map

| Python (carrycode) | Lines | TypeScript (dsh-carryon) | Notes |
| --- | ---: | --- | --- |
| `records.py` | 101 | `src/records.ts` | pydantic → zod schemas; same JSON field names |
| `registry.py` | 107 | `src/registry.ts` | versioned carrier store, candidate registry |
| `validator.py` | 64 | `src/validator.ts` | same problem strings (parity tests compare them) |
| `view.py` (render, projection, step texts) | 97 | `src/view.ts` | boundary helpers come from dsh, not ported |
| `tracker.py`, `compiler.py` | 175 | `src/roles.ts` | prompts loaded from shared files |
| `llm.py` | 75 | `src/llm.ts` | over `ctx.llm.stream()` instead of LiteLLM |
| `runtime.py` (`fold`) | 168 | `src/engine.ts` | inside `summarize()`; trigger logic not ported (dsh owns it) |
| `prompts/tracker.md`, `compiler.md` | 245 | `prompts/` | copied verbatim from carrycode, see §6 |

About 800 lines of Python become an estimated 900–1200 lines of TS plus tests. Not ported: `agent.py`,
`cli.py`, `swebench.py`, `pro_grade.py`, `metrics.py`, `grounder/`.

## 6. Keeping two runtimes in step

- **Prompts.** carrycode's `src/carrycode/prompts/*.md` is the source of truth. `dsh-carryon` vendors them
  with a recorded commit and a CI check that fails when the hashes differ from that commit. The rule against
  copying the paper's Appendix D applies to both repos. Do not reuse dsh's own compaction instruction either:
  CarryOn's roles need their own prompts.
- **Parity fixtures.** A new carrycode script (`scripts/export_parity_fixtures.py`) writes JSON cases:
  input messages, prior state, scripted Tracker/Compiler replies → expected carriers, execution context,
  rendered checkpoint text, validator problems. Both test suites run every case; the TS suite reads the
  fixtures from a pinned carrycode commit.
- **Versioned state.** `CarryOnState.v` lets both sides reject state they do not understand instead of
  misreading it.

## 7. Packaging

```
dsh-carryon/
├── package.json        # dsh.bundle.patch, engines.dsh, peerDependencies on @deepseek-ai/dsh-*
├── cordis.patch.yml    # replaces the compaction-basic row with CarryOnCompactionEngine
├── prompts/            # vendored from carrycode
├── src/
└── tests/              # unit tests (mocked ctx.llm) + parity fixtures
```

- dsh packages the plugin shares with the host go in both `peerDependencies` and `devDependencies`, as the
  dsh publishing guide asks.
- `engines.dsh` pins a narrow range (e.g. `>=0.2.2-alpha.2 <0.3.0`). CI runs against the pinned version and,
  allowed to fail, against dsh `main`, because dsh is in developer preview and announces breaking changes.
- Install: `dsh plugin add dsh-carryon` (or `file:` / `link:` during development); check with
  `dsh --dump-config`.

## 8. Milestones

| Step | Done when |
| --- | --- |
| P0 Spike | A `summarize()` override that returns a fixed text compacts a real dsh session in the Web UI; the patch row swap works; we know whether `rawOutput` is shown in the UI. |
| P1 Core port | records, registry, validator, view in TS; parity fixtures from carrycode pass. |
| P2 Roles + engine | Tracker/Compiler over `ctx.llm`; state round-trips through `rawOutput`; failed fold leaves the surface unchanged (test with mocked LLM). |
| P3 Dogfood | Long sessions in the Web UI; compare token use against `compaction-basic` on the same tasks. |
| P4 Release | README (install, config, differences from carrycode, "not benchmarked"), npm publish, `dsh-plugin` topic. |

## 9. Open questions

1. Exact `cordis.patch.yml` operation to replace (not add next to) the `compaction-basic` row; only `insert`
   was seen in the docs read so far. P0 answers this.
2. Is `compaction/summary.rawOutput` rendered or exported anywhere a user sees it?
3. Session API for reading the latest `compaction/summary` event inside `summarize()` (via `agent.session`).
4. Does `/compact` (manual, `compactNow`) also go through `summarize()`? Expected yes, since it is the only
   hook; confirm in P0.
5. Is `BasicCompactionEngine` exported for subclassing from the package root in released builds
   (`export class BasicCompactionEngine` exists in `src/index.ts`)?
