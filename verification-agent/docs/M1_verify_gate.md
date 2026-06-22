# M1 — The verify gate (the truth gate)

> **State: IMPLEMENTED.** Proven on Code4rena `2024-01-decent` @ `5d1962143ee5`.
> Recorded run: [`examples/m1_decent_gate_run.txt`](../examples/m1_decent_gate_run.txt).

The verify gate is the load-bearing component of the whole system: **a finding
is surfaced only if it is fork-executed into a reproducing PoC.** Everything
upstream (hypotheses, path-finding) is allowed to be noisy because the gate is
the thing that refuses to pass anything it cannot prove.

The hard part is not "run a test". It is making sure the gate proves the
*specific claimed invariant break* — not merely that a test passed or a
transaction did something. A gate that only checks "did it pass" is a compile
check, and it will happily launder a hallucination into a finding.

## What the gate keys on: an independent invariant predicate

Every case defines an **invariant predicate** — a Solidity function
`_invariantHolds()` over protocol state, defined *independently of the attack*.
The PoC author supplies the scenario and the attack, **but cannot decide the
verdict.** The gate decides it by evaluating that one predicate across four
phases (see [`VerifyGate.sol`](../verification_agent/verify/solidity/VerifyGate.sol)):

| Phase | Check | If it fails |
|---|---|---|
| 1. **Baseline** | invariant holds on honest seeded state | `REJECTED_MALFORMED_BASELINE` — a predicate false at rest can't witness a break |
| 2. **Control** | a legitimate, authorized action *preserves* it | `REJECTED_MALFORMED_CONTROL` — a predicate that honest use breaks would confirm anything |
| 3. **Attack** | run the candidate exploit (revert is caught) | — |
| 4. **Verdict** | re-evaluate the *same* predicate | see below |

Phase-4 outcomes:

- invariant **broken** → `CONFIRMED`
- invariant intact **and attack reverted** → `REJECTED_ATTACK_REVERTED` (false hypothesis)
- invariant intact **and attack succeeded** → `REJECTED_INVARIANT_INTACT`
  — the **wrong-reason catch**: the PoC changed on-chain state but did not
  violate the stated invariant.

### Why this is sound (sketch)

The three guards make the predicate itself hard to game:

- An **always-true** predicate can never reach `CONFIRMED` — phase 4 can't break it.
- An **always-false** predicate is caught at **baseline**.
- A predicate that is true at rest but **breaks under any state change** (the
  failure mode that would "confirm" the wrong-reason case) is caught at
  **control**, because an honest action breaks it.

What survives all three and still breaks under the attack is a genuine,
execution-proven invariant violation. That, and only that, is `CONFIRMED`.

These are not just arguments — the baseline and control guards are **proven
firing** by two demonstrator cases (D and E below) that deliberately feed the
gate bad *measuring sticks* and watch it refuse. An untested guard is a guard
trusted on faith; the demonstrators are the regression tests that catch a
too-tight predicate written in a hurry mid-contest, before it can yield a false
`CONFIRMED`.

## The five cases (M1 self-proof)

Anchored on `2024-01-decent` — the same contest M0 modeled — so the gate is
validated against the exact codebase. Cases A–C share one scenario and one
sound invariant (`target.pwnedCount == feesCollected / FEE`, i.e. *every
privileged swap-execute is fee/signature gated*), differing only in
`runAttack()`. Cases D–E reuse the scenario but install a deliberately **broken
predicate** to prove the gate audits its own measuring stick.
Source: [`solidity/DecentFeeBypass.t.sol`](../verification_agent/verify/solidity/DecentFeeBypass.t.sol).

Cases A–C test bad *exploits*; D–E test bad *predicates*. Together they exercise
every non-trivial corner of the verdict taxonomy.

### Case A — known-true (must CONFIRM)
**C4 2024-01-decent M-03** (issue #590). `UTB.receiveFromBridge` is `public`
with no access control and calls `_swapAndExecute` directly, skipping the
`retrieveAndCollectFees` modifier that validates the fee/swap-instruction
signature via `UTBFeeCollector.collectFees`. The attack executes a swap+payload
with **no signature and no fee**.
**Asserts:** baseline `0==0`; control (one paid, signed swap) `1==1`; attack
(`receiveFromBridge`) makes executions `2` while fees-paid stays `1` →
invariant broken → **CONFIRMED**.

### Case B — flatly false (must reject, nothing reproduced)
Hypothesis: "a forged ECDSA signature passes `collectFees` and bypasses the fee
check in `swapAndExecute`." It does not — `require(recovered == signer)` holds
and the call reverts.
**Asserts:** attack reverts, state unchanged, invariant intact →
**REJECTED_ATTACK_REVERTED**.

### Case C — passes for the wrong reason (must reject *despite* changing state)
This is the one that separates this gate from a hallucinating auditor. The PoC
performs a **fully-valid, fully-PAID** `swapAndExecute` and *claims* it proves a
fee bypass. The transaction **succeeds and changes on-chain state** (a payload
executes AND a fee is collected). A naive "did the tx do something?" gate would
mark this confirmed.
**Asserts:** attack succeeds (no revert), executions `2` and fees-paid `2` →
invariant **intact** → **REJECTED_INVARIANT_INTACT**.

### Case D — malformed baseline (must reject the predicate, not the exploit)
The predicate is false on honest seeded state (`feeCollector.balance > 0` at
rest). A predicate false at baseline cannot witness a break.
**Verdict:** `REJECTED_MALFORMED_BASELINE` — the attack is never reached.

### Case E — malformed control (the guard that audits the measuring stick)
The predicate `target.pwnedCount == 0` holds at baseline but is too brittle: any
legitimate, fully-paid swap breaks it by design. If the gate trusted it, the
attack phase would yield a false `CONFIRMED`. Control catches it first.
**Verdict:** `REJECTED_MALFORMED_CONTROL` — the attack is never reached. This is
the last load-bearing guard, now proven firing rather than asserted.

## Recorded result

All five corners of the verdict taxonomy, proven on camera
([`examples/m1_decent_gate_run.txt`](../examples/m1_decent_gate_run.txt) + the
structured [`examples/m1_decent_gate_run.json`](../examples/m1_decent_gate_run.json)
which carries the predicate text judged for each verdict):

```
[OK] known_true         DecentReceiveFromBridgeBypass  expected CONFIRMED                   -> CONFIRMED
[OK] false_hypothesis   DecentForgedSignatureFalse     expected REJECTED_ATTACK_REVERTED    -> REJECTED_ATTACK_REVERTED
[OK] wrong_reason       DecentPaidSwapWrongReason       expected REJECTED_INVARIANT_INTACT   -> REJECTED_INVARIANT_INTACT
[OK] malformed_baseline DecentMalformedBaseline        expected REJECTED_MALFORMED_BASELINE -> REJECTED_MALFORMED_BASELINE
[OK] malformed_control  DecentMalformedControl         expected REJECTED_MALFORMED_CONTROL  -> REJECTED_MALFORMED_CONTROL

summary: 5/5 gate verdicts correct; 1 CONFIRMED finding(s).
```

At backtest scale, a run where `MALFORMED_*` verdicts occasionally appear is
*healthier* than one where they never do: it means the gate is still policing
predicates under real conditions, not rubber-stamping. The structured run log
(`--json`) records every verdict with the predicate it judged, which is the
artifact that demonstrates this.

## Run it

```bash
# clone the target once (pinned), then:
python -m verification_agent verify --repo /path/to/2024-01-decent --json run.json
```

Requires `forge` on PATH and a reachable/staged `solc` (see STATUS.md → environment notes).

## Notes on trust and the DEGRADED model (carried from M0)

A regex-tagged surface from M0's lite fallback is a **lead, not a finding**.
When Slither could not compile the target, the model feeding hypotheses is
softer, so the gate matters *more*, not less. The gate does not trust M0 tags at
all — it re-derives truth from execution. Tags without Slither provenance should
never be promoted past the gate on the strength of the tag alone.

## What M1 deliberately does NOT do yet

- **Generate** the PoC. M1 cases are hand-written; the milestone is proving the
  gate, not authoring exploits. PoC generation arrives with the hypothesis
  engine (M3) and path backends (M4) and will emit the same `VerifyGate`-shaped
  cases the gate already rules on.
- **Minimize** the PoC or assign final severity — that is triage (M5).
- **Fork live mainnet.** Cases use a focused local deployment of the real
  in-scope contracts. The harness env (`FOUNDRY_OFFLINE`, staged solc) is built
  for fork/local execution; never against live value.
