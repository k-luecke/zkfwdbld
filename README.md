# zkfwdbld

`zkfwdbld` is a prototype trust layer for `verified findings` and, more
broadly, for `trustworthy agentic actions`.

Today it combines a Rust/Wasm proving core, AO-oriented orchestration, and
local evaluation tooling to explore how findings from existing security tools
can be encoded, verified, and handed off with more trust than a black-box
scanner alert. The longer-term direction is broader: attach structured trace,
verification state, and handoff-ready artifacts to autonomous actions that
organizations need to trust.

The project currently has three main parts:

- A Rust core that generates witnesses and verifies R1CS constraints over the
  Goldilocks field.
- AO-oriented Lua and Node tooling for deployment, cutover, and message routing.
- Local evaluation and experiment utilities for scoring, baselining, and
  performance measurement.

## Product Direction

The most promising first market is AppSec teams that struggle to trust automated
findings enough to act on them quickly.

The immediate wedge is:

`a verification and trace layer for automated security workflows`

The broader thesis behind the project is:

`verification and audit infrastructure for agentic actions`

Instead of replacing existing scanners or agents, the system should sit on top
of them and produce:

- a source-aware normalized finding
- a normalized claim
- the evidence used
- a trace of how the claim was derived
- a proof artifact
- a verification result
- a triage-ready summary for engineers

Over time, that same product shape can expand beyond findings into higher-risk
agent actions such as code changes, operational workflows, or customer-facing
automation.

The product wedge and MVP plan are documented in:

- [docs/market_positioning.md](docs/market_positioning.md)
- [docs/agent_trust_positioning.md](docs/agent_trust_positioning.md)
- [docs/second_action_family.md](docs/second_action_family.md)
- [docs/next_build_decision.md](docs/next_build_decision.md)
- [docs/mvp_verified_findings.md](docs/mvp_verified_findings.md)
- [docs/mvp_adapter_layer.md](docs/mvp_adapter_layer.md)

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
- `docs/`: proof contract, market positioning, and MVP planning

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

## Adapter Demo

Run the current trust-layer adapter demo with:

```sh
node examples/adapter_demo.mjs
```

This emits one canonical `verified_finding` artifact shape from three different
inputs:

- synthetic harness finding
- mocked scanner finding
- mocked agent finding

Run the mocked scanner path with:

```sh
node examples/scanner_to_artifact.mjs
```

Run the first supported scanner prove/verify path with:

```sh
node examples/scanner_to_artifact.mjs verified
```

Run the human-readable scanner report with:

```sh
node examples/scanner_report.mjs verified
```

Export scanner findings as shareable markdown and JSON bundles with:

```sh
node examples/export_scanner_reports.mjs verified
```

## Harness Artifact Demo

Run the real harness-to-artifact path with:

```sh
node examples/harness_to_artifact.mjs
```

This scans the actual
[phase0_form_workflow.html](/home/kyle_w_luecke/zkfwdbld/harness/phase0_form_workflow.html)
fixture and emits canonical `verified_finding` artifacts from the matches.

Run the first supported prove/verify path with:

```sh
node examples/harness_to_artifact.mjs verified
```

Today, `HIDDEN_INPUT` is the first supported claim family. In `verified` mode,
hidden-input findings are deterministically encoded, proved, and verified
through the Rust bridge, while other finding families remain clearly labeled as
demo-only.

This currently works from two source types:

- synthetic harness findings
- mocked scanner-export findings

Run the human-readable harness report with:

```sh
node examples/harness_report.mjs verified
```

Export harness findings as shareable markdown and JSON bundles with:

```sh
node examples/export_harness_reports.mjs verified
```

The generated reports now include handoff-oriented fields such as:

- recommended action
- trust rationale
- open questions
- report-level handoff readiness

## Agent Action Demo

Run the first non-AppSec action-family scaffold with:

```sh
node examples/message_actions.mjs reviewed
```

This demonstrates the first `agent_action` path for outbound message review,
using bounded send-policy states like `ready_to_send` and `needs_review`.

Export this action family as markdown and JSON bundles with:

```sh
node examples/export_message_reports.mjs
```

## Polsia Demo Packet

Build the current best customer-facing packet with:

```sh
node examples/build_polsia_packet.mjs
```

This writes:

- `overview.md`
- `demo_talk_track.md`
- `packet_manifest.json`
- a verified harness bundle
- a verified scanner bundle
- an outbound message action bundle

under `artifacts/polsia-demo-packet/`.

## Deployment Notes

The repo includes multiple AO deployment and spawn scripts from active
experimentation. The most important operational scripts today are:

- `build_wasm.sh`
- `deploy_paxiom.js`
- `cutover.mjs`

The deployment path is still being consolidated, so treat the scripts as
operator tooling for an evolving prototype rather than a finalized release flow.
