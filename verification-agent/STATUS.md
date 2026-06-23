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
| **M3 — Hypothesis engine** | **IMPLEMENTED** (offline; protocol-aware) / **PARTIAL** (Claude) | M0 surface + M2 priors → EV-ranked candidate hypotheses whose primary output is a gate-survivable invariant predicate. Proposes-never-confirms enforced structurally (no `verify` import; `is_candidate` only; LLM confidence zero-weight). **Move 2 — protocol-aware generation (default):** a hypothesis targets a violation of the protocol's own STATED RULE (a guarded sibling enforces modifier M over effect E; here is a path reaching E without M), not a generic "unguarded" shape. Measured by **confirmed-to-leads ratio**: Decent **0.143 → 0.250** (7→4 leads, M-03 retained); Centrifuge **62 → 0 leads** (silent on the design-permissionless false positives, no real structural finding lost). Rules are PRIORS, not truth. See [docs/M3_hypothesis_engine.md](docs/M3_hypothesis_engine.md). |
| **M4 — Path backends** | **IMPLEMENTED** (Seer) / **PARTIAL** (Medusa/Halmos) | Seer structural-reachability engine independently rediscovers the M-03 path (`receiveFromBridge` bypassing `retrieveAndCollectFees`) from the M0 model alone; handed to the M1 gate it CONFIRMS — machine-found path, machine verdict. Medusa (1.5.1) + Halmos (0.3.3) wired behind the same interface; coverage is environment-bounded and logged honestly. No `verify` import (wall). See [docs/M4_path_backends.md](docs/M4_path_backends.md). |
| **M4.5 — Scenario synthesis** | **IMPLEMENTED** (pipeline + Control guarantee + deploy-graph discovery + signature keystone) / **FRONTIER** (rest of the semantic mile; EIP-712) | Synthesizes a gate scenario from a lead and runs it through the **byte-for-byte real** gate — no fast path. Proven: **faithful → CONFIRMED**, **rigged → REJECTED_MALFORMED_CONTROL**. **Deploy-graph synthesis** derives the collaborator deploy+wiring backbone from the M0 model; the **signature keystone** (`SignatureSchemeSynthesizer`) detects the verifier's scheme (EIP-191) and **constructs** the Control's signature — no hand sig. Spliced together they **CONFIRM Decent M-03 against real code** (calibration); a *wrong* scheme reverts Control (`REJECTED_MALFORMED_CONTROL_REVERT`) — the guard fires. Full-scenario autonomy moved **19% → 31%** (8/26 statements), closing the previously-named core blocker. EIP-712 detected-but-not-emitted (the permit frontier). Centrifuge structural leads **refuted against real code** — honest negative; blind Tier-1 is a **bug-class coverage** gap, **stays 0**. See [docs/M4.5_scenario_synthesis.md](docs/M4.5_scenario_synthesis.md). |
| M5 — Triage + report | PROPOSED | Severity (C4/Sherlock/Cantina), uniqueness fingerprint, PoC minimize, draft. (Built after M6 per build order.) |
| **M6 — Backtest harness** | **IMPLEMENTED** | **FROZEN** three-tier taxonomy pinned before the run (Tier-1 path+verdict / Tier-2 +PoC-synth / Tier-3 surfaced) — a found path without a gate verdict is **not** a catch. Blind run (`BlindRunner` never reads answer keys; scorer opens them after freeze), lane-curated set (Decent calibration + Centrifuge **blind**). Honest result: **Tier-1 1/8 (0.125, the calibration M-03; blind Tier-1=0)**, surfaced recall **0.75**, 3 Seer leads (not catches). The number says *surfacer+verifier today, build M4.5 before a live contest*. See [docs/M6_backtest.md](docs/M6_backtest.md). |

## Module-level state (M0)

| Module | State | Notes |
|---|---|---|
| `ingest/clone.py` | IMPLEMENTED | Clone + pin commit + recursive submodules. |
| `ingest/build.py` | IMPLEMENTED (Foundry) / PARTIAL (Hardhat) | Foundry first-class; Hardhat detected + compiled, modeling tuned for Foundry. |
| `model/slither_runner.py` | IMPLEMENTED | Contracts, inheritance, entry points, storage vars, call graph. Storage *slots* left null (exact packing needs `forge inspect`) — labeled, not guessed. Robust to Foundry projects that need `out/build-info`: on Slither failure it generates build-info and retries with `ignore_compile` (lets the M0 pipeline model fresh contests offline — proven on 2023-11-kelp). |
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
| `hypothesize/protocol_rules.py` | IMPLEMENTED | Move 2: extracts the protocol's stated rules (guarded-sibling modifier asymmetry over a real internal effect; + NatSpec authority scan) and their violations. Drives protocol-aware generation. Target-agnostic (no protocol literal; asserted). Raises confirmed-to-leads ratio on Decent, silences Centrifuge's false positives. |
| `pathfind/seer.py` | IMPLEMENTED | Structural-reachability engine; rediscovers the M-03 path from the M0 model. |
| `pathfind/{medusa,halmos}.py` | PARTIAL | Stateful-fuzz + symbolic adapters; tools installed; coverage environment-bounded, logged honestly. |
| `pathfind/orchestrator.py` | IMPLEMENTED | Dispatches backends; builds the per-backend/per-mechanism coverage map. No `verify` import. |
| `backtest/tiers.py` | IMPLEMENTED (frozen) | The pinned three-tier taxonomy; `classify` is mechanical and has no `path_found` parameter (a lead is not a catch). `FROZEN_RULES` asserted by the scorer. |
| `backtest/contests.py` | IMPLEMENTED | Lane-curated contest registry + `ANSWER_KEYS` (opened only by the scorer). Decent = calibration, Centrifuge = blind. |
| `backtest/runner.py` | IMPLEMENTED | `BlindRunner` runs M0→M3→M4→M1 on code alone; never reads findings. |
| `backtest/scorer.py` | IMPLEMENTED | Opens answer keys post-freeze, applies `classify`, aggregates lane-only recall per tier. |
| `screen/shape.py` | IMPLEMENTED | Move A: shape-fit pre-screen. Scores a codebase for the alt-entrypoint bug-class SHAPE from structure alone (M0 surface + Move-2 sibling-asymmetry + Seer reachability). Keys on **Seer-pathability** (the Kelp discriminator): Decent **HIGH** (0.9, M-03 pathable), Kelp **LOW** (0.2, 0 pathable). Never reads findings; runs on settled OR live scope (dual-use contest selection). |
| `screen/findings.py` | IMPLEMENTED | Move B: fetch (git `<contest>-findings`) + parse a Code4rena `report.md` into the scorer's ANSWER_KEYS format. id/title/severity exact; hosts+mechanism heuristic (flagged). Validated on the REAL 2024-01-decent report (all 9 H/M recovered, ids match the curated key). Wall intact: the BlindRunner never reads answer keys (asserted). |
| `synthesize/templates.py` | IMPLEMENTED | Target-agnostic Solidity template for the alt-entrypoint-gated-effect mechanism; emits a faithful + a rigged variant. No protocol names (asserted by test). |
| `synthesize/synthesizer.py` | IMPLEMENTED | Lead → `SynthScenario`; enforces the honest boundaries (self-contained ≠ real; signature-scope leads refused with the gap named). |
| `synthesize/runner.py` | IMPLEMENTED | Drops the byte-for-byte real `VerifyGate.sol` + the synthesized scenario into a workspace and runs the unchanged four-phase gate. Requires forge + forge-std. |
| `synthesize/deploygraph.py` | IMPLEMENTED (discovery) | Derives a target's collaborator deploy+wiring from the M0 model (owner-gated setters → concrete contracts; interfaces excluded; mock slots named). Emits an autonomy ledger naming the semantic mile it cannot derive. Proven execution-correct on Decent M-03 (5/6 backbone lines autonomous). |
| `synthesize/signature.py` | IMPLEMENTED (EIP-191/raw) | Detects the verifier's signing scheme from its source and emits a Solidity signer that **constructs** the Control's signature (digest reconstruction + `vm.sign` + fixture key). Target-agnostic (no protocol literal; asserted). EIP-712 detected but not emitted. Proven on Decent M-03 (CONFIRMED), with a wrong-scheme negative control that reverts Control. |

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
