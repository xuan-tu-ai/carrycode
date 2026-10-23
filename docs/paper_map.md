# Paper to code map

Paper: arXiv:2610.18784v2 (14 Oct 2026).

| Paper | Concept | Module | Status |
| --- | --- | --- | --- |
| §3.2, Eq. (1) | Context view V = (A, E, L) | `view.py`, `agent.py::CarryOnAgent.build_view` | done (skeleton) |
| §3.3 Eq. (2), Π(L_t) | Live-tail text projection | `view.py::project_tail` | done |
| §3.2 | Three carrier types | `records.py::CarrierType` | done |
| App. A.1 | Candidate records, versioned carriers, claims | `records.py`, `registry.py` | done |
| §3.3 "Tracking Candidates" | Tracker, compile requests | `tracker.py` | done (M1) |
| §3.3 "Preparing Evidence" | Evidence package U_t | `compiler.py::EvidencePackage` | log evidence done (M1); Grounder evidence M2 |
| App. A.2, Table 6 | Grounder checks and verdicts | `grounder/` | verdicts done; coding checks drafted |
| §3.3 "Joint Compilation", Eq. (2) | Compiler | `compiler.py` | done (M1) |
| §3.3 "Validation and Commitment" | Validator, atomic commit | `validator.py`, `registry.py::apply` | done (M1, without Grounder verdicts) |
| App. A.3 "Runtime triggering" | Trigger at ~6,000 new tokens (chars/4) | `runtime.py::should_fold` | done |
| App. B.3 | Per-task token and cost accounting | `metrics.py::trajectory_usage` | done |
| Table 4 | Sliding-window baseline | `agent.py::SlidingWindowAgent` | done |
| Table 5 | Hide carriers / hide EC ablations | not planned | — |

## Known differences from the paper

- Domain: SWE-bench coding tasks instead of OSWorld 2.0 / BrowseComp-Plus.
- Grounder runs tests, compilation and `git diff` in the task container.
- Host and runtime models are Claude Haiku 5.5 (via Token Harbor), not Claude Opus 4.7.
- After a fold the live tail is empty. The paper's OSWorld adapter also kept recent
  screenshots and a pending assistant message (App. A.3); coding has no screenshots.
- The Compiler proposes CarrierEdits; the runtime assigns ids and versions (see decisions.md).
