# MVP Spec: Adapter Layer

## Goal

Position `zkfwdbld` as a trust layer that sits on top of existing AppSec tools
 rather than a replacement for them.

This should also be treated as the first adapter-layer pattern for a broader
agent-trust system, not only a one-off AppSec integration story.

The first customer-facing promise becomes:

`Use the tools you already trust for detection. Use zkfwdbld to add verifiable
trace, structured evidence, and proof status to the findings that matter.`

## Product Shape

Input:

- a finding from an existing scanner, agent, or workflow tool

Output:

- a normalized finding record
- evidence trace
- proof or demo-proof status
- verification result
- triage-ready artifact

## Why This Wedge Is Better

- lower buying friction because no rip-and-replace is required
- easier design-partner conversations
- more realistic first demos
- clearer connection to existing AppSec pain: trust, traceability, handoff

## MVP Architecture

The MVP should introduce five product concepts:

### 1. Source Adapter

Accepts upstream findings from a tool-specific source.

Examples:

- synthetic harness adapter
- mocked scanner export adapter
- mocked agent-output adapter

Longer term, the same adapter model should be able to accept action records
from broader agentic systems, not only scanners.

### 2. Normalized Claim

Converts upstream findings into one internal schema.

This schema should capture:

- source tool
- source finding id
- target
- pattern family
- raw evidence
- normalized claim
- contextual metadata

### 3. Evidence Trace

Captures the chain of inputs used to produce the result.

This is the customer-visible trust payload:

- what tool reported the finding
- what evidence was used
- what transformation occurred
- what proof path was attempted

### 4. Proof / Verification Layer

Runs when the finding family is supported.

Trust states should include:

- `verified`
- `demo_only`
- `unsupported`
- `unsat`
- `error`

### 5. Artifact Emitter

Produces the final output object for downstream systems.

This artifact should be stable enough to:

- render in a UI later
- attach to tickets later
- review in JSON now

## First Demo Set

The first marketable demos should show:

### Demo 1

`Synthetic harness finding -> zkfwdbld verified finding artifact`

Purpose:

- prove the internal architecture
- show the shape of the output

### Demo 2

`Mock scanner finding -> zkfwdbld verified finding artifact`

Purpose:

- show compatibility with existing AppSec tooling
- reinforce that zkfwdbld is a layer, not a replacement

### Demo 3

`Mock agent-generated finding -> zkfwdbld verified finding artifact`

Purpose:

- show the strongest trust-layer use case
- demonstrate that black-box agent outputs can become inspectable

## MVP Deliverables

1. A normalized finding artifact schema.
2. An adapter interface for upstream findings.
3. One synthetic adapter.
4. One mocked real-tool adapter.
5. One mocked agent-output adapter.
6. One consistent artifact emitted from all three.
7. Explicit trust-state labeling in every artifact.

## Non-Goals

Do not try to support many real integrations at once.

The MVP does not need:

- production SaaS integrations
- bidirectional ticket sync
- dashboard UX
- many proof families
- generalized security data lake ingestion

## Recommended Build Order

1. Define the canonical finding artifact schema.
2. Define the source adapter interface.
3. Implement synthetic harness adapter.
4. Implement mocked scanner adapter.
5. Implement mocked agent adapter.
6. Emit one shared artifact shape for all three.
7. Add one demo route or CLI that shows the three inputs and one output model.
