# Next Build Decision

## Decision

The next build after the current packet-ready state should be:

`a real inbound adapter`

not a UI-first pass.

## Why

The project now has:

- a credible product thesis
- a packet-level demo
- two action families
- human-readable handoff artifacts
- exportable bundles

What it does not yet have is a real non-native upstream source feeding the new
agent-action path.

That means the next highest-leverage question is not presentation polish.
It is whether the trust-layer model still feels strong when connected to a real
workflow input instead of a mocked one.

## Recommendation

Build one real inbound adapter for the outbound-message action family before
building a UI.

The ideal target is something narrow and low-risk, such as:

- a structured email draft source
- a CRM export
- a support-message draft feed
- a JSON handoff from an internal agent workflow

## Why Adapter Before UI

### 1. It tests the thesis, not just the presentation

A UI can make the current prototype easier to show, but a real adapter tests
whether the product survives contact with real upstream data.

### 2. It improves credibility faster

The strongest next proof point is:

`this trust artifact was produced from a real workflow input`

That matters more than a prettier surface.

### 3. The current packet is already good enough for design-partner demos

You already have:

- overview framing
- talk track
- handoff docs
- machine-readable artifacts

That is enough to run early conversations while the underlying source realism
improves.

### 4. UI is safer after the artifact model settles

The current artifact surface is still expanding from findings to broader agent
actions.

It is better to let that shape stabilize through one more real adapter before
locking into a UI surface too early.

## What This Means Practically

The next sprint should aim for:

1. one real inbound adapter for outbound messages
2. one export path from that adapter into the existing artifact model
3. one updated Polsia packet that includes the real adapter path

Only after that should the project decide whether the next step is:

- a lightweight browser UI
- a static HTML viewer
- or staying packet-first a little longer

## Summary

The current product now looks believable.

The next thing it needs is not a nicer face. It needs one more piece of real
world contact.

So the right next build is:

`real inbound adapter first, UI second`
