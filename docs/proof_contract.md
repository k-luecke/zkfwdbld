# Seer Proof Contract

This document defines the intended production contract for the Seer proof path.
The current orchestrator still contains a demo-only CNF encoder; any result from
that path must be treated as a prover smoke test, not as a causation proof.

## Request Contract

A production proof request must bind these values into the generated constraint
system:

- `fact`: the exact extracted page/header finding.
- `context`: the page URL, level, pattern family, and finding offset.
- `claim`: the specific assertion being proved for the pattern family.
- `cnf`: the generated constraints for that assertion.
- `seed`: deterministic coefficient seed used by both prover and verifier.

The verifier must be able to reconstruct the same constraints from the same
`fact`, `context`, `claim`, and `seed`.

## Result Contract

A proof result may be routed as a causation proof only when:

- the request used a production encoder, not the demo CNF,
- the prover returned `success=true`,
- the prover returned `satisfiable=true`,
- the correlation id matches a pending request,
- the result came from the configured prover process.

Demo-mode results may be logged or returned as diagnostics, but they must not be
reported as a level-clear or causation proof.

## Current Demo Boundary

The current `agent.lua` path emits a fixed SAT sample formula for detected
findings. That confirms message flow and prover liveness only. It does not prove
that the scanned finding causes, enables, or validates an application behavior.

Before production use, replace the demo encoder with a pattern-family encoder
that derives constraints from the observed finding and context.
