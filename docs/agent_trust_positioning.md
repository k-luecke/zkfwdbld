# Agent Trust Positioning

## Thesis

`zkfwdbld` has a larger opportunity than verified AppSec findings alone.

If agents can spend money, message customers, ship code, open tickets, modify
infrastructure, or run operations, then trust becomes a core market need.

The hard questions are:

- why did the agent take this action?
- what evidence did it rely on?
- what policy or constraints should have applied?
- did it stay inside those constraints?
- can a human inspect the action after the fact?
- can an organization trust this automation enough to let it keep operating?

`zkfwdbld` should be thought of as infrastructure for those questions.

## Product Category

The long-term product category is:

`verification and audit infrastructure for agentic actions`

This is broader than AppSec and more native to the current shape of the
project.

The system should eventually help organizations attach structured trace,
constraint awareness, and verifiable artifacts to autonomous or semi-autonomous
actions.

## Why Now

Agentic systems are becoming capable of:

- calling tools
- spending budgets
- sending customer-facing messages
- writing and shipping code
- changing operational state
- acting across multiple systems without a human in the loop

The black-box problem gets worse as blast radius rises.

Organizations need a way to distinguish:

- actions that are inspectable and bounded
- actions that are only heuristically justified
- actions that should be blocked, reviewed, or rolled back

## What zkfwdbld Can Become

At maturity, `zkfwdbld` could sit between:

- an agent or autonomous workflow
- the tools it can invoke
- the policies it should obey
- the audit or review layer downstream

and produce:

- a normalized action record
- an evidence trace
- a claim about what happened
- a statement of applicable constraints
- a verification result for supported action families
- a human-readable handoff or audit artifact

## Action Types In Scope

Potential action families over time:

- security findings
- code changes
- production configuration changes
- outbound customer messages
- pricing or refund actions
- workflow approvals or denials
- support operations

The project should not pretend to solve all of these at once.

The right move is to support a narrow set of high-trust actions first and grow
the verification surface carefully.

## First Wedge

The current first wedge remains useful:

`verified findings for automated AppSec workflows`

This is still a good entry point because it is:

- concrete
- painful
- easy to explain
- close to current repo capabilities
- a credible example of the broader trust problem

So the right framing is:

`agent trust infrastructure, starting with verified findings`

## Product Promise

The larger promise should be:

`zkfwdbld helps organizations understand which agent-produced actions are ready
for execution, handoff, or audit, and why.`

That promise is stronger than "we generate proofs."

The customer outcome is not cryptography by itself. The customer outcome is:

- less black-box automation
- clearer trust boundaries
- faster safe handoff
- stronger auditability
- more confidence in policy-sensitive agent behavior

## Important Boundaries

This product should not be marketed as:

- universal agent safety
- proof of all model reasoning
- a complete solution to prompt injection
- a guarantee that all autonomous behavior is correct

It should be marketed as:

- structured verification for selected high-risk action families
- trust and audit infrastructure for supported autonomous actions
- a way to make some automation more inspectable and governable than it is now

## Near-Term Product Direction

Near term, the repo should continue to build:

1. stable artifacts
2. explicit trust states
3. human-readable handoff reports
4. adapter layers for upstream tools and agents
5. at least one real verified action family

Then expand from findings toward a second action family that is closer to
general agent operations.

## Strategic Summary

The AppSec wedge is the opening move.

The broader company thesis is:

`as agents become real economic actors, zkfwdbld becomes part of the trust
infrastructure that makes those actors governable.`
