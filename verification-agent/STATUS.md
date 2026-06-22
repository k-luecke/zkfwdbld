# Build status

Honest, per-module state. Labels: **IMPLEMENTED** / **PARTIAL** / **PROPOSED** /
**SPECULATIVE**. The build order is load-bearing — each milestone runs
end-to-end against a settled contest before the next is started. Do not let any
report imply more certainty than the verify gate (M1) has established.

## Milestones

| Milestone | State | Notes |
|---|---|---|
| **M0 — Harness** | **IMPLEMENTED** | Clone @ commit, Foundry build, Slither extract, JSON model + tagged verification surface. Proven on `code-423n4/2024-01-decent`. |
| **M1 — Verify gate** | **PROPOSED** | *Build next.* Given a hand-written hypothesis, generate + run a Foundry fork test, report verifiable pass/fail. Must confirm one known PoC and reject one bogus one before anything upstream is trusted. |
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
| `cli.py` | IMPLEMENTED | `model` command only. No hypothesis/exploit commands until M1 is trusted. |

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
