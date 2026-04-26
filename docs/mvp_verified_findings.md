# MVP Spec: Verified Findings

## Goal

Turn `zkfwdbld` from a prover-oriented prototype into a narrow product for AppSec
teams: verified findings for automated security workflows.

This MVP should assume `zkfwdbld` is a trust layer on top of existing tools.

## MVP Outcome

A user submits or captures one supported security-relevant observation, either
directly or through an adapter from an upstream tool.

The system returns:

- a normalized finding
- the claim being made
- the evidence used
- a proof artifact
- a verification result
- a triage-ready explanation

The current implementation also includes a human-readable report renderer on top
of the canonical artifact so design-partner demos can show triage output instead
of raw JSON alone.

## First Supported Use Case

Start with one use case only:

`hidden or workflow-derived credential hint detected in a controlled web
interaction`

Current implementation status:

- `HIDDEN_INPUT` now has a deterministic claim encoder and local prove/verify path
- `HIDDEN_INPUT` is supported from both harness and mocked scanner sources
- other finding families remain demo-only

Why this one:

- it fits the current harness and orchestrator shape
- it is close to the current pattern vocabulary
- it can be demoed clearly
- it gives us a concrete finding story before broadening to more classes

## MVP User Flow

1. A source finding is submitted.
2. The adapter normalizes it into the internal claim schema.
3. The claim encoder converts that finding into a real claim payload.
4. The prover produces a witness and proof artifact.
5. The verifier reconstructs the claim and verifies the result.
6. The system emits a triage artifact for the AppSec user.

## User-Facing Artifact

The MVP should produce one stable output object or report with:

- finding id
- source tool
- source finding id
- target url or workflow id
- pattern family
- claim text
- evidence snippet
- trace metadata
- proof status
- verifier status
- timestamp
- confidence or support level

If the proof path is demo-only, the artifact must say so clearly.

## Required Product Work

### 1. Replace demo claim path

The current static CNF stub must be replaced for the first supported finding
family.

Minimum requirement:

- claim generation must be deterministic from finding + context
- verifier must reconstruct the same claim inputs
- non-production claim paths must be explicitly labeled

### 2. Add finding artifact schema

Create a stable JSON schema for a verified finding report.

It should be simple enough to:

- render in a UI later
- export to a ticket later
- review in a terminal today

### 3. Add verifier-first output

The customer should not have to inspect raw witness bytes.

The system should emit:

- human-readable summary
- machine-readable artifact
- verification outcome

### 4. Add trust states

We need explicit states:

- `verified`
- `demo_only`
- `unsupported_claim`
- `unsat`
- `error`

This prevents overclaiming.

### 5. Add one end-to-end integration test

The first product test should cover:

- source finding in
- finding normalized
- claim encoded
- proof generated
- verification completed
- triage artifact emitted

### 6. Add one adapter interface

The MVP should define a thin adapter contract for upstream tools so the product
story is clearly "works with your stack."

## Non-Goals For MVP

Do not expand MVP scope yet into:

- many finding families
- a dashboard product
- multi-tenant auth
- deep AO infra abstraction
- generalized proof marketplace language

## Success Criteria

We should call the MVP ready for design-partner conversations when:

- one supported claim path is genuinely real end to end
- the output artifact is understandable to a security engineer
- the demo can be explained in under two minutes
- the system clearly distinguishes verified from demo-only outputs
- performance is acceptable for interactive triage
- at least two different input sources can produce the same artifact shape

## Suggested Build Order

1. Define the canonical verified-finding artifact.
2. Define the first adapter interface.
3. Define the first supported claim family precisely.
4. Replace the static CNF path for that family.
5. Emit verifier-first outputs.
6. Add an end-to-end integration test.
7. Add one mocked non-native source adapter.
