# Build status

Honest, per-module state. Labels: **IMPLEMENTED** / **PARTIAL** / **PROPOSED** /
**SPECULATIVE**. The build order is load-bearing — each milestone runs
end-to-end against a settled contest before the next is started. Do not let any
report imply more certainty than the verify gate (M1) has established.

## Milestones

| Milestone | State | Notes |
|---|---|---|
| **M0 — Harness** | **IMPLEMENTED** | Clone @ commit, Foundry build, Slither extract, JSON model + tagged verification surface. Proven on `code-423n4/2024-01-decent`. |
| **M1 — Verify gate** | **IMPLEMENTED** | Truth gate: invariant-keyed, 4-phase (baseline/control/attack/verdict). Proven on `2024-01-decent` with 5 cases (5/5) covering every verdict corner — confirms the real M-03 finding; rejects a false hypothesis, a wrong-reason PoC (state changes, invariant intact), and two malformed *predicates* (false-at-baseline, broken-by-honest-use) that prove the Baseline/Control guards fire. Structured `--json` run log carries the predicate per verdict. See [docs/M1_verify_gate.md](docs/M1_verify_gate.md). |
| M2 — Knowledge base | PROPOSED | OAK matrix + settled-contest corpus into a local vector store for RAG. |
| M3 — Hypothesis engine | PROPOSED | Claude + KB + invariants → ranked candidate hypotheses (EV = severity × novelty ÷ verify-cost). |
| M4 — Path backends | PROPOSED | Seer (structural reachability) + Halmos (symbolic) + Medusa/Echidna (fuzz) behind one interface. Highest risk: must reproduce a *known* finding end-to-end. |
| M5 — Triage + report | PROPOSED | Severity (C4/Sherlock/Cantina), uniqueness fingerprint, PoC minimize, draft. |
| M6 — Backtest harness | PROPOSED | Full loop over 10–15 settled contests → recall/precision/uniqueness. The deliverable number. |

## Module-level state (M0)

| Module | State | Notes |
|---|---|---|
| `ingest/clone.py` | IMPLEMENTED | Clone + pin commit + recursive submodules. |
| `ingest/build.py` | IMPLEMENTED (Foundry) / PARTIAL (Hardhat) | Foundry first-class; Hardhat detected + compiled, modeling tuned for Foundry. |
| `model/slither_runner.py` | IMPLEMENTED | Contracts, inheritance, entry points, storage vars, call graph. Storage *slots* left null (exact packing needs `forge inspect`) — labeled, not guessed. |
| `model/surface.py` | IMPLEMENTED | The specialization filter. Heuristic + evidence; precision improves via the LEARN loop. |
| `model/lite.py` | PARTIAL | Regex fallback when Slither can't compile. Approximate by design; output flagged DEGRADED. |
| `model/model_builder.py` | IMPLEMENTED | Orchestrates the stages; records tool provenance in `tool_status`. |
| `cli.py` | IMPLEMENTED | `model` (M0) and `verify` (M1) commands. No hypothesis/exploit-generation commands until M3/M4. |
| `verify/VerifyGate.sol` | IMPLEMENTED | On-chain 4-phase truth gate; verdict keyed on an independent invariant predicate. |
| `verify/harness.py` | IMPLEMENTED | Installs gate templates into a target, runs `forge test`, parses the on-chain verdict. |
| `verify/gate.py`, `cases.py` | IMPLEMENTED | Verdict taxonomy + the 3-case M1 self-proof registry. PoCs are hand-written (M1); generation lands in M3/M4. |

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
