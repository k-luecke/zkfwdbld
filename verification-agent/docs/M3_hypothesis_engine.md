# M3 — The hypothesis engine (proposes; never confirms)

> **State: IMPLEMENTED** (offline generator) / **PARTIAL** (Claude generator —
> wired, not exercised here: no API key / blocked network).
> Demo: [`examples/m3_decent_hypotheses.txt`](../examples/m3_decent_hypotheses.txt)
> (+ structured [`.json`](../examples/m3_decent_hypotheses.json)).

M3 connects M0's verification surface and M2's mechanism priors into a ranked
batch of **candidate hypotheses** that flow into the M1 gate. Two design
commitments govern it.

## 1. M3 proposes; it never confirms (a structural wall)

This is the same boundary M2 enforces (`is_verdict = False`), held harder here
because an LLM enters the loop and LLMs are confident.

- A `Hypothesis` has **no verdict field** and cannot express one; `is_candidate`
  is always `True` ([schema.py](../verification_agent/hypothesize/schema.py)).
- The LLM's `llm_confidence` is **advisory metadata with zero weight on any
  verdict**. `ev.score_ev()` has no `confidence` parameter — a hypothesis the
  model is 99% sure of and one it's 30% sure of are handed to the gate
  identically. The gate only cares whether the invariant breaks under execution.
- **Nothing in `hypothesize/` imports the verify gate** — enforced by a test
  (`test_hypothesize_does_not_import_the_gate`). The only path from a hypothesis
  to a verdict runs through M1, which re-derives truth by execution.

The LLM's job is to *aim* the gate at good targets; it never vouches for what it
aims at. The handoff (proposes → verify) lives in the orchestrator
(`cli._connect_gate`), not inside the package.

## 2. The predicate is the primary output

The most valuable thing M3 produces is not the attack sketch — it's a
**well-formed, mechanism-specific invariant predicate** that survives the gate's
Baseline and Control phases. A great attack idea with a sloppy predicate just
yields `MALFORMED_CONTROL` rejections. Predicate quality is M3's real output
metric, and the gate is how it's measured.

Each hypothesis carries an `InvariantSpec` with explicit
baseline / control / break expectations, produced by the invariant pattern
library ([invariants.py](../verification_agent/hypothesize/invariants.py)) keyed
on the KB-grounded mechanism. The library covers the brief's invariant classes:
authorization-conservation, caller-authenticity, replay-resistance,
signature-authenticity, proof-soundness, solvency/accounting-conservation,
stake-set-consistency.

### The loop is real

Running the engine on the Decent surface, the gate-bound hypothesis for the
real M-03 function emits this predicate:

> **authorization-conservation** — count(privileged-effect) == count(authorized-invocations)
> baseline: `0 == 0`; control: one paid call → `1 == 1`; break: attacker triggers the effect → effects > authorizations.

That is exactly the M1 gate's invariant (`target.pwnedCount == feesCollected/FEE`).
Handed to the gate (`hypothesize --connect-gate`), it **clears baseline and
control and returns CONFIRMED**:

```
[connect-gate] handing 'UTB.receiveFromBridge' to the M1 gate via case DecentReceiveFromBridgeBypass
  hypothesis predicate: authorization-conservation (count of privileged effect vs count of authorized invocations)
  gate verdict: CONFIRMED  (predicate cleared baseline+control: True)
  -> the engine PROPOSED the target+predicate; the GATE decided truth.
```

The discovery layer and the truth gate are connected. M3 generated the target
and the measuring stick; M1 alone decided it was real.

## 3. EV ranking earns its keep against an over-inclusive surface

M0 deliberately over-tags (recall bias), so the surface contains benign
functions. EV must deprioritize them cheaply
([ev.py](../verification_agent/hypothesize/ev.py)):

```
EV = severity x evidence / verify_cost
  severity  = bug-class severity (access-control/signature/proof rank high)
              x blast-radius factor (down-weighted when the function has no
              external call and no verification-keyword surface)
  evidence  = 0.7 * KB-prior-match strength + 0.3 * structural risk
  verify_cost = grows with attack-sketch length
```

The **blast-radius factor** is the key to the recall-bias tradeoff: a function
flagged purely structurally that only writes its own state (no external/low-level
call, no keyword surface) can't reach a privileged cross-contract effect, so it
doesn't inherit a real access-control bug's full severity. On the fixture surface,
the benign `contribute()` sinks to the floor (EV 0.076) below every real
verification-surface function — demonstrating the requirement the recall bias
wrote.

### Honest scope of the ranking

Within the *structurally identical* class of unguarded external-call
entrypoints, EV cannot fully separate the real bug (`receiveFromBridge`) from
legitimate siblings (`UniSwapper` swaps) — they genuinely look alike at
retrieval time (the swaps even hosted M-01). That separation is exactly the
gate's job. **EV gets you to the right neighborhood cheaply; the gate
adjudicates within it.** On the Decent surface the signature/access-control
cluster correctly tops the queue and the benign floor is correctly demoted; the
gate then confirms M-03 and would reject a benign sibling.

## Providers

- **Offline** ([provider.py](../verification_agent/hypothesize/provider.py)) —
  deterministic, KB-grounded; makes the whole loop runnable with no network.
- **Claude** — wired per the current Anthropic SDK (model `claude-opus-4-8`,
  adaptive thinking, a `strict` tool schema for structured output). It produces
  the same `Hypothesis` schema and is the stronger generator when the API is
  reachable; it is not exercised in this environment. Same boundary: its
  confidence is advisory; it never touches the gate.

## Move 2 — protocol-aware generation (the hunter got sharper)

The original engine reasoned from **structure alone**: every function on the
recall-biased surface became a lead. That cannot tell a real violation from a
legitimately permissionless function — which is why it was loud on unfamiliar
code (Centrifuge surfaced 62 structural leads, all design-permissionless).

Move 2 makes a hypothesis target a violation of the protocol's **own stated rule**
([protocol_rules.py](../verification_agent/hypothesize/protocol_rules.py)). The
protocol *states* a rule whenever its code gates an effect: a guarded sibling `G`
reaches an internal effect `E` while carrying a modifier `M` (auth, *or* a
fee/precondition gate). That is the claim "reaching `E` requires `M`". A
**claimed-rule violation** is an entrypoint `F` reaching the same `E` *without* `M`
— a real lead ("the protocol claims only-via-M causes E; here is not-M causing E"),
versus "F is unguarded", which is noise. The filter excludes trivial shared callees
(control-flow, `_msgSender`, getters, type-converters, builtins) — exactly the
trivia that paired siblings into noise before. Rules are **priors, not truth**
(a stated rule is "worth testing whether this holds", never established fact); the
gate still adjudicates.

**The metric is confirmed-to-leads ratio, not lead count.** A change that raises
leads without raising the ratio made the hunter *worse*. Measured on the two
contests with known answers (`examples/move2_protocol_aware.txt`):

| Contest | Before (structure) | After (protocol-aware) |
|---|---|---|
| **Decent** | 7 leads, 1 confirmed → **0.143** | 4 leads, 1 confirmed → **0.250** (M-03 retained, 3 junk dropped) |
| **Centrifuge** | 62 leads, 0 confirmed | **0 leads** — silent on the false positives |

Decent's ratio rose 1.75× by *shrinking the denominator* while keeping the M-03
hypothesis. Centrifuge went to **0** structural-bypass violations — correct, not a
miss: its real findings are non-structural (cross-domain / signature / missed at
M0), the known bug-class coverage gap, and the 62 prior leads were all
design-permissionless false positives now suppressed.

**NatSpec probe (honest):** prose-only authority claims (a rule stated in comments
but not in a modifier) numbered **0** on both contests — the stated rules are all in
modifiers, which the asymmetry signal already captures; NatSpec only *corroborates*
(M-03 and `bridgeAndExecute` carried authority comments). So on this evidence
modifier-asymmetry is the workhorse and NatSpec-as-generator did not move the ratio;
the hook is in place for protocols that state rules only in prose.

Protocol-aware is the default; `protocol_aware=False` reproduces the structural
generator (used to measure before/after, and by the tests that cover that path).

## Run it

```bash
python -m verification_agent hypothesize --model model.json --top 10
python -m verification_agent hypothesize --model 2024-01-decent.model.json \
       --connect-gate /path/to/2024-01-decent      # proposes -> gate handoff
```

## What M3 does NOT do yet

- **Generate the PoC.** M3 emits the target + predicate + attack *sketch*;
  turning the sketch into compiled Solidity for an arbitrary target is M4 (path
  backends: Seer / Halmos / Medusa). For M-03 the predicate maps to the existing
  hand-built M1 case, which is how the loop is demonstrated end-to-end today.
- **Minimize or assign final severity** — that is triage (M5).
