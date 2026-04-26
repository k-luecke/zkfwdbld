# Market Positioning

## Larger Thesis

`zkfwdbld` is best understood as emerging trust infrastructure for agentic
systems.

If agents can act in the world by producing findings, shipping code, messaging
customers, or running operations, then organizations need better ways to audit
why those actions happened and whether they stayed inside policy.

That larger thesis is documented in
[docs/agent_trust_positioning.md](docs/agent_trust_positioning.md).

## Primary Wedge

`zkfwdbld` should be positioned first as a trust layer for AppSec teams that do
not trust automated findings enough to act on them quickly.

The product is not "a zk prover" in the buyer's mind. The product is:

`a verification and trace layer for automated AppSec workflows`

This wedge is the first concrete expression of a broader category:

`verification and audit infrastructure for agentic actions`

That means the value proposition is not cryptography for its own sake. The value
proposition is:

- fewer false-positive escalations
- faster triage of high-confidence findings
- a clear audit trail for why the system made a claim
- easier engineer handoff because the claim is structured and reproducible
- no requirement to replace existing scanners or agent workflows

## Ideal Customer Profile

First buyer:

- AppSec lead or product security leader
- startup to mid-market, or infra-heavy engineering org
- already using scanners, agentic testing, or internal automation
- frustrated by noisy results and manual validation
- technical enough to appreciate a trust layer

Strong early-fit examples:

- Box
- GitLab
- Pure Storage
- Alteryx

## Core Problem

Most automated security tools fail at the moment of trust.

They can produce large numbers of findings, but the user still has to ask:

- Is this real?
- Why does the tool think it is real?
- Can I hand this to engineering without embarrassment?
- Can I explain this in an audit or review later?

`zkfwdbld` should exist to answer those questions as a layer on top of existing
tools, not as a rip-and-replace security platform.

## Product Promise

`zkfwdbld` helps AppSec teams trust automated findings by attaching a verifiable,
structured proof and trace artifact to findings produced by the tools they
already use.

## What We Are Not Selling

We are not initially selling:

- general-purpose proving infrastructure
- a broad zero-knowledge platform
- generic autonomous security agents
- a full compliance operating system
- a replacement scanner

Those may become adjacent opportunities later, but they are not the first wedge.
The near-term job is to enter through one concrete pain point while preserving
the larger trust-infrastructure identity.

## Messaging Hierarchy

Top-line:

`Trust automated security findings enough to act on them`

Supporting points:

- keep your existing tools
- prove why a finding was produced
- reduce manual re-validation for high-confidence results
- give engineers a structured, inspectable artifact instead of a vague alert
- preserve an audit trail for security review and postmortem analysis

## Competitive Angle

Relative to ordinary scanning and agent tooling:

- less black-box
- more inspectable
- more reproducible
- easier to defend internally
- designed to complement existing tooling rather than replace it

Relative to raw security research tools:

- closer to a workflow
- easier to demo to buyers
- tied to an operational outcome rather than a theorem

## First Product Story

Input:

- a finding from a scanner, agent, or workflow observation source

Output:

- a structured finding
- a source trace
- a confidence level
- a proof artifact
- a verification result
- an explanation payload suitable for AppSec triage

The first customer-facing story should be:

`Your existing tools found this. zkfwdbld made it easier to trust, verify, and
route to engineering.`

The broader strategic story behind that wedge is:

`As autonomous systems take higher-impact actions, zkfwdbld helps teams see
which actions are ready for execution or handoff, and why.`
