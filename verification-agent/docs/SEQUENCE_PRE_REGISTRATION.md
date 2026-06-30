# Sequence run — pre-registration of known confounds

Written BEFORE the Sequence run, so that artifacts the run *will*
produce can be recognized when read rather than mistaken for either
signal or new bugs. A known confound you've pre-named is readable; the
same confound unnamed is the unreadable-result trap one level down.

## Confound #1 — `Root.pause` shape / OR-authorized-path false positives in protocol-aware leads

**What it looks like in the output.** Protocol-aware leads where the
hypothesis target reaches a privileged effect that is *also* reached by
another in-scope function carrying a different modifier, and the
protocol's intent is "EITHER guard is acceptable" (not "all guards
required"). Concrete shape seen on Centrifuge after the 2026-06-30
precision-regression fix:

  - Effect: `Root.pause`
  - Two reachers: `DelayedAdmin.pause` (guarded by `auth`) and
    `PauseAdmin.pause` (guarded by `canPause`)
  - Protocol's authorization scheme: "Root.pause is callable by
    `auth`-wards directly OR via `canPause`-protected `PauseAdmin.pause`"
  - The extractor produces TWO violations:
      * "PauseAdmin.pause reaches Root.pause without `auth`" (rule
        inferred from DelayedAdmin's path)
      * "DelayedAdmin.pause reaches Root.pause without `canPause`" (rule
        inferred from PauseAdmin's path)
  - Both are false positives — the protocol intends dual-path
    authorization, the `all-guards-required` rule model can't represent it.

**Why it's not in scope to fix.** The fix is a rule-model change (from
`all-guards-required` to `at-least-one-guard-conserved`) — a deeper
extractor redesign that opens the surface area clause-4 of the precision
fix scope contract was built to keep closed. Doing it before Sequence
is exactly the while-we're-here trap that turns one defect into a week
of polishing.

**How to read it during Sequence.** If a Sequence protocol-aware lead has
the shape "target T reaches effect E without modifier M, where some
guarded sibling G of T also reaches E with M", **check if there exists
another in-scope function H that reaches E with a different modifier
M'**. If yes, the lead is the Root.pause shape — a known OR-authorized
artifact, not signal. Note it, do not count it as a violation candidate
the gate should adjudicate. Specifically:

  - **Do not** advance such a lead through the gate-confirmation path —
    even if the gate gives a verdict, the verdict will be against a
    rule that doesn't exist as a protocol invariant
  - **Do not** treat the lead's absence-from-confirmed as evidence of
    "missed bug" — the rule doesn't exist to be missed
  - **Do** count the lead's *non-Root.pause-shape* peers normally — this
    confound is per-lead, not per-run

**Pre-registered count cap.** On a substrate-comparable target the size
of Centrifuge (58 contracts, 200 entry points), the post-fix output
yielded 2 leads of this shape. A Sequence run producing more than ~10
Root.pause-shape leads is itself a signal — either the contest's
authorization design is unusually dual-pathed, or there's a secondary
mechanism producing similar shapes. Note count in the FREEZE notes;
do not let an inflated count quietly recategorize anything.

## Confound #2 — Centrifuge M-04 / M-08 host coverage

**What it looks like.** The 2026-06-30 audit re-keyed Centrifuge M-04
to access-control (was `dos`) and tightened M-08's hosts. The substrate
surfaces M-04 (`LiquidityPool.deposit, LiquidityPool.mint`) but MISSES
M-08 (`RestrictionManager.detectTransferRestriction`). M-08 missed
because the structural surface tagger doesn't yet have a heuristic for
"returns an enum/code instead of revert" style restriction implementations.

**Why it's not in scope.** Improving the surface tagger is a substrate
enhancement, not a precision fix. Out of scope for the readable-Sequence
condition.

**How to read it during Sequence.** Not directly relevant to Sequence —
this is a Centrifuge-specific observation. Recorded here so that if
Sequence's contest has an ERC1404-style restriction layer, you know in
advance the substrate won't surface it well.

## Pre-registered acceptance state for Sequence

Substrate state on which Sequence will run:

| Component | State at pre-registration |
|---|---|
| Whole-program call graph | ✓ hardened (commit be99c40), library callees marked structurally |
| Slither IR-tuple handling | ✓ fixed (commit 2ce3105) |
| Seer internal-sink preference | ✓ fixed (commit 2ce3105) |
| Scorer qualified identifiers | ✓ fixed (commit 1d321a2) |
| Whole-program call graph | ✓ multi-hop (commit be99c40) |
| Tool version stamping in FREEZE | ✓ (commit c8ff900) |
| Answer-key three-field re-audit | ✓ done; floor 0.833 surfaced / 0.167 TIER-1 on n=6 in-lane (commit 1593098) |
| Systematic mis-keying bias documented | ✓ (commit 250f04e) |
| Protocol-aware precision (Centrifuge) | ✓ under budget (87 → 2, decent M-03 lead preserved) |
| Root.pause / OR-authorized-path | **pre-registered known confound (this doc)** |
| Sequence-specific run-book | TODO before run |

The honest list of known-broken components in the substrate Sequence
will run on is **empty**. The Root.pause shape is pre-registered, not
broken — its outputs are readable. Anything else that surfaces during
Sequence and doesn't match this pre-registration is either signal or a
new finding the substrate produced — both deserve full attention, not
either ambiguous-result handling or quiet relabeling.

## What this document does NOT pre-commit

- Specific Sequence numbers (recall, TIER-1 count, surfaced ratio)
- Specific contracts or functions the substrate will or won't surface
- The verdict on whether the substrate "works"

The Sequence run produces those; this document just makes sure they're
readable when they come back.
