# Build status

Honest, per-module state. Labels: **IMPLEMENTED** / **PARTIAL** / **PROPOSED** /
**SPECULATIVE**. The build order is load-bearing — each milestone runs
end-to-end against a settled contest before the next is started. Do not let any
report imply more certainty than the verify gate (M1) has established.

## Milestones

| Milestone | State | Notes |
|---|---|---|
| **M0 — Harness** | **IMPLEMENTED** | Clone @ commit, Foundry build, Slither extract, JSON model + tagged verification surface. Name-independent **structural** recall rule (unguarded privileged entrypoint) closes the entry-point recall gap: **9/9** judged 2024-01-decent High/Mediums have their host on the surface (6/9 by keywords alone). See [docs/M0_recall.md](docs/M0_recall.md). |
| **M1 — Verify gate** | **IMPLEMENTED** | Truth gate: invariant-keyed, 4-phase (baseline/control/attack/verdict). Proven on `2024-01-decent` with 5 cases (5/5) covering every verdict corner — confirms the real M-03 finding; rejects a false hypothesis, a wrong-reason PoC (state changes, invariant intact), and two malformed *predicates* (false-at-baseline, broken-by-honest-use) that prove the Baseline/Control guards fire. Structured `--json` run log carries the predicate per verdict. See [docs/M1_verify_gate.md](docs/M1_verify_gate.md). |
| **M2 — Knowledge base** | **IMPLEMENTED** | Lane-curated, mechanism-structured, dual-source (OAK taxonomy + contest/incident worked examples). Mechanism-feature retrieval (fields ~0.86, lexical ~0.14); a prior is never a verdict. On the M-03 surface the real M-03 + same-class priors top the list while a bridge/fee vocabulary decoy ranks #18/20. See [docs/M2_knowledge_base.md](docs/M2_knowledge_base.md). |
| **M3 — Hypothesis engine** | **IMPLEMENTED** (offline) / **PARTIAL** (Claude) | M0 surface + M2 priors → EV-ranked candidate hypotheses whose primary output is a gate-survivable invariant predicate. Proposes-never-confirms enforced structurally (no `verify` import; `is_candidate` only; LLM confidence zero-weight). On Decent the M-03 predicate clears the gate's baseline+control and CONFIRMS; benign `contribute()` is demoted to the EV floor. See [docs/M3_hypothesis_engine.md](docs/M3_hypothesis_engine.md). |
| **M4 — Path backends** | **IMPLEMENTED** (Seer) / **PARTIAL** (Medusa/Halmos) | Seer structural-reachability engine independently rediscovers the M-03 path (`receiveFromBridge` bypassing `retrieveAndCollectFees`) from the M0 model alone; handed to the M1 gate it CONFIRMS — machine-found path, machine verdict. Medusa (1.5.1) + Halmos (0.3.3) wired behind the same interface; coverage is environment-bounded and logged honestly. No `verify` import (wall). See [docs/M4_path_backends.md](docs/M4_path_backends.md). |
| M5 — Triage + report | PROPOSED | Severity (C4/Sherlock/Cantina), uniqueness fingerprint, PoC minimize, draft. (Built after M6 per build order.) |
| **M6 — Backtest harness** | **IMPLEMENTED** | **FROZEN** three-tier taxonomy pinned before the run (Tier-1 path+verdict / Tier-2 +PoC-synth / Tier-3 surfaced) — a found path without a gate verdict is **not** a catch. Blind run (`BlindRunner` never reads answer keys; scorer opens them after freeze), lane-curated set (Decent calibration + Centrifuge **blind**). Honest result: **Tier-1 1/8 (0.125, the calibration M-03; blind Tier-1=0)**, surfaced recall **0.75**, 3 Seer leads (not catches). The number says *surfacer+verifier today, build M4.5 before a live contest*. See [docs/M6_backtest.md](docs/M6_backtest.md). |

## Module-level state (M0)

| Module | State | Notes |
|---|---|---|
| `ingest/clone.py` | IMPLEMENTED | Clone + pin commit + recursive submodules. |
| `ingest/build.py` | IMPLEMENTED (Foundry) / PARTIAL (Hardhat) | Foundry first-class; Hardhat detected + compiled, modeling tuned for Foundry. |
| `model/slither_runner.py` | IMPLEMENTED | Contracts, inheritance, entry points, storage vars, call graph. Storage *slots* left null (exact packing needs `forge inspect`) — labeled, not guessed. |
| `model/surface.py` | IMPLEMENTED | The specialization filter: keyword tags (vocabulary) **plus** a name-independent structural rule (`tag_structural`) for unguarded privileged entrypoints. Evidence + confidence on every tag. |
| `model/lite.py` | PARTIAL | Regex fallback when Slither can't compile. Approximate by design; output flagged DEGRADED. |
| `model/model_builder.py` | IMPLEMENTED | Orchestrates the stages; records tool provenance in `tool_status`. |
| `cli.py` | IMPLEMENTED | `model` (M0) and `verify` (M1) commands. No hypothesis/exploit-generation commands until M3/M4. |
| `verify/VerifyGate.sol` | IMPLEMENTED | On-chain 4-phase truth gate; verdict keyed on an independent invariant predicate. |
| `verify/harness.py` | IMPLEMENTED | Installs gate templates into a target, runs `forge test`, parses the on-chain verdict. |
| `verify/gate.py`, `cases.py` | IMPLEMENTED | Verdict taxonomy + the 5-case M1 self-proof registry. PoCs are hand-written (M1); generation lands in M3/M4. |
| `kb/store.py`, `schema.py` | IMPLEMENTED | Mechanism-feature retriever; `PriorMatch` is prior-only (`is_verdict=False`). |
| `kb/embedder.py` | IMPLEMENTED (lexical) / PROPOSED (neural) | Lexical tiebreaker behind an `Embedder` protocol; neural/Chroma backend pluggable but unused (offline). |
| `kb/data/*.jsonl`, `tools/build_corpus.py` | IMPLEMENTED | Curated dual-source corpus; editable JSONL is the source of truth. Access-control entries carry the structural surface tag (M0↔M2 alignment). |
| `hypothesize/{engine,provider,invariants,ev}.py` | IMPLEMENTED | M3 engine; offline + Claude providers; invariant pattern library; EV ranking. No `verify` import (structural wall). |
| `pathfind/seer.py` | IMPLEMENTED | Structural-reachability engine; rediscovers the M-03 path from the M0 model. |
| `pathfind/{medusa,halmos}.py` | PARTIAL | Stateful-fuzz + symbolic adapters; tools installed; coverage environment-bounded, logged honestly. |
| `pathfind/orchestrator.py` | IMPLEMENTED | Dispatches backends; builds the per-backend/per-mechanism coverage map. No `verify` import. |
| `backtest/tiers.py` | IMPLEMENTED (frozen) | The pinned three-tier taxonomy; `classify` is mechanical and has no `path_found` parameter (a lead is not a catch). `FROZEN_RULES` asserted by the scorer. |
| `backtest/contests.py` | IMPLEMENTED | Lane-curated contest registry + `ANSWER_KEYS` (opened only by the scorer). Decent = calibration, Centrifuge = blind. |
| `backtest/runner.py` | IMPLEMENTED | `BlindRunner` runs M0→M3→M4→M1 on code alone; never reads findings. |
| `backtest/scorer.py` | IMPLEMENTED | Opens answer keys post-freeze, applies `classify`, aggregates lane-only recall per tier. |

## Known limitations (M0)

- **Storage slots** are listed by declaration, not packed-slot-resolved.
- **Verification surface is recall-biased**: expect over-tagging (e.g. a generic
  `claim` flagged as a bridge handler). Every tag carries evidence for the
  operator to prune. Precision is a LEARN-loop concern, not an M0 blocker.
- **Hardhat path** compiles but downstream modeling is Foundry-tuned.
- The **lite fallback** is not a Solidity parser and makes no correctness claims.

## Environment notes

- Requires `forge`/`anvil` on PATH and a reachable `solc`. Where the public
  Solidity binary host is blocked, stage solc binaries from the Solidity GitHub
  releases into `~/.svm/<version>/solc-<version>` and run Foundry with
  `FOUNDRY_OFFLINE=true`.
