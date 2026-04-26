# zkfwdbld

`zkfwdbld` is a prototype Rust/Wasm prover and AO orchestration repo for
encoding small SAT-style claims as an R1CS witness flow.

The project currently has three main parts:

- A Rust core that generates witnesses and verifies R1CS constraints over the
  Goldilocks field.
- AO-oriented Lua and Node tooling for deployment, cutover, and message routing.
- Local evaluation and experiment utilities for scoring, baselining, and
  performance measurement.

## Current Status

This repository is a serious prototype, not a production proof system yet.

The Rust prover path is tested and actively hardened, but the orchestrator still
contains a demo-only CNF path. That means end-to-end "proof" messages currently
demonstrate liveness and flow, not a fully bound real-world causation proof.

The current proof boundary is documented in
[docs/proof_contract.md](docs/proof_contract.md).

## Repository Layout

- `src/`: Rust prover, R1CS builder, field encoding, witness generation
- `agent.lua`: AO orchestrator / routing layer
- `seer_eval/`: scoring, classification, audit, and baseline helpers
- `harness/`: local HTML harness for controlled workflow tests
- `examples/`: small runnable experiments
- `experiments/`: captured experiment outputs and notes
- `Heuristics/`: research notebooks, benchmark inputs, and exploratory material

## Local Verification

Rust tests:

```sh
cargo test
```

Node evaluator tests:

```sh
node tests/test_seer_eval.mjs
```

Formatting check:

```sh
cargo fmt --check
```

## Prover Scaling Experiment

Run the current scaling example with:

```sh
cargo run --release --example prover_scaling
```

The first captured run is stored in
[experiments/prover_scaling_2026-04-26.csv](experiments/prover_scaling_2026-04-26.csv).

That experiment is useful for separating the two main costs:

- witness generation growth with variable count
- R1CS build and verify growth with clause count

## Deployment Notes

The repo includes multiple AO deployment and spawn scripts from active
experimentation. The most important operational scripts today are:

- `build_wasm.sh`
- `deploy_paxiom.js`
- `cutover.mjs`

The deployment path is still being consolidated, so treat the scripts as
operator tooling for an evolving prototype rather than a finalized release flow.
