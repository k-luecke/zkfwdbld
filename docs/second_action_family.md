# Second Action Family

## Goal

Choose the first non-AppSec action family that `zkfwdbld` should support after
verified findings.

This decision matters because it turns the broader "agent trust
infrastructure" thesis into an actual roadmap rather than a positioning-only
 story.

## Selection Criteria

The second action family should be:

- closer to general agent operations than a security finding
- easy to explain to a non-security audience
- high enough trust value to matter
- narrow enough to model with explicit constraints
- low enough blast radius for early experimentation
- compatible with the current artifact, trace, and handoff model

## Candidates Considered

### 1. Outbound customer message approval

Example:

- an agent drafts or sends a customer-facing email, support reply, or outreach
  message

Why it is attractive:

- easy for non-technical buyers to understand
- obviously policy-sensitive
- already common in agent workflows
- naturally supports "ready to send" vs "needs review" trust states

Risks:

- free-form text semantics are harder to verify cleanly
- proving message quality is much harder than proving bounded structure
- can drift into subjective evaluation quickly

### 2. Code change risk classification

Example:

- an agent proposes a code change and `zkfwdbld` emits a structured action
  artifact saying whether the change stayed inside a bounded policy

Why it is attractive:

- close to current developer and agentic-code zeitgeist
- very relevant to autonomous software systems
- strong future potential

Risks:

- semantics are broad and high complexity
- hard to define one narrow first claim family
- large implementation surface before the first credible demo

### 3. Ticket creation or workflow routing decision

Example:

- an agent opens a ticket, assigns an owner, or routes an operational issue
  according to policy

Why it is attractive:

- easy to model as a bounded action
- lower blast radius than money movement
- easy to attach evidence and handoff semantics
- very compatible with the current report surface

Risks:

- can feel operationally useful but less exciting as a flagship demo
- may not fully showcase the policy-sensitive nature of agent actions

### 4. Budget-bound spend approval

Example:

- an agent decides whether to approve or execute a spend below a bounded
  threshold

Why it is attractive:

- extremely clear trust story
- high perceived value
- naturally policy-driven

Risks:

- too high stakes for an early prototype
- difficult to demo responsibly without overclaiming
- can create more fear than confidence in early conversations

## Recommendation

The recommended second action family is:

`outbound customer message approval`

More precisely:

`policy-aware verification and handoff for agent-generated outbound messages`

## Why This One

This is the best next step because it balances:

- broad relevance beyond AppSec
- strong trust sensitivity
- intuitive buyer understanding
- a narrow enough action shape for early support

It is a cleaner bridge from "verified findings" to "trustworthy agent actions"
than code changes or spending decisions.

It also maps directly onto the larger thesis:

- an agent wants to act in the world
- the action has reputational and operational risk
- a human or system needs to know whether that action is safe to proceed
- `zkfwdbld` can produce a structured artifact saying what was attempted, what
  policy applied, what evidence existed, and whether the action is ready for
  handoff or execution

## Narrow First Scope

Do not try to verify arbitrary message quality.

The first supported message-action family should be something constrained like:

`agent-generated outbound message satisfies an explicit send policy`

Example policy dimensions:

- recipient domain is allowlisted
- no disallowed promises or pricing claims are present
- required disclosure string is included
- message type matches the approved template family
- confidence state is explicit

That keeps the first claim family grounded in bounded constraints rather than
subjective persuasion quality.

## Proposed Product Shape

Input:

- draft outbound message
- recipient metadata
- policy metadata
- message source metadata

Output:

- normalized action artifact
- message evidence
- applied policy summary
- verification status
- handoff decision such as `ready_to_send` or `needs_review`
- human-readable rationale

## Trust States

For this action family, useful states could be:

- `ready_to_send`
- `needs_review`
- `unsupported_policy`
- `policy_failed`
- `error`

These can coexist with the repo-wide verification states, but the user-facing
surface should use language that matches the action.

## Why Not Code Changes First

Code-change verification is still important, but it should probably come after
one cleaner non-security action family.

Outbound message approval is easier to explain, easier to demo, and easier to
connect to the larger market thesis quickly.

## Suggested Build Order

1. Define a canonical `agent_action` artifact variant or extension.
2. Define one outbound-message adapter input shape.
3. Define one narrow send-policy schema.
4. Implement a mocked message-action demo path.
5. Reuse the report and handoff layers for `ready_to_send` vs `needs_review`.
6. Only then decide whether to generalize the artifact surface beyond findings.

## Decision Summary

If verified findings are the first wedge, then outbound message approval should
be the second action family.

That gives `zkfwdbld` a credible progression:

`verified findings -> trustworthy agent messages -> broader agent action
governance`
