# Precision-regression diagnosis — protocol-aware leads on Centrifuge (2026-06-30)

## What's being diagnosed

The xfail introduced by the 2026-06-30 audit:

> `tests/test_protocol_rules.py::test_protocol_aware_goes_quiet_on_centrifuge_false_positives`
> protocol-aware mode now yields **87 leads** vs **62 non-protocol-aware**
> (test budget: < 15, i.e. <25% of pre-protocol count)

The richer whole-program call graph (commit `be99c40`, edges 600 → 796,
qualified callees 253 → 651) turned the *precision* mechanism into a
noise generator on Centrifuge.

## Method

Three-field rigor applied per lead, not pattern-match. For each lead:
- **Host** — does `target_contract.target_function` exist and is it
  externally callable?
- **Claimed rule** — does the guarded sibling actually enforce the
  modifier before reaching the effect, and is the effect itself a real
  privileged state-changing function?
- **Unguarded path** — does the target actually reach the effect WITHOUT
  the modifier in source?

REAL = all three pass; SPURIOUS = any fails.

Sampling rule (per the scope sharpening): read until population is
characterized as real / spurious / mixed, **not** a fixed 5–10. If the
first reads land on one population, keep going until the ratio stabilizes
or both kinds are observed.

## What I actually had to read

Before any source reads, the lead structure itself collapsed the
population: **all 87 leads pair on only 7 distinct "effects"**, and 6 of
the 7 are categorically non-effects on their face. The remaining one
turned out spurious for a different reason. Counts:

| Effect | Lead count | Effect category |
|---|---:|---|
| `Auth.auth` | 48 | modifier name |
| `ERC20.auth` | 9 | modifier name |
| `Gateway.pauseable` | 9 | modifier name |
| `MathLib.mulDiv` | 9 | pure library function |
| `low_level_call` | 7 | sentinel string for low-level calls |
| `BytesLib.slice` | 4 | pure library function |
| `BytesLib.toUint8` | 1 | pure library function |
| **Total** | **87** |  |

The raw `protocol_rules.extract_rules_and_violations` produces 145
violations (deduped to 87 by the hypothesis engine). Same shape, with
one extra effect category worth noting: `SafeTransferLib.safeTransferFrom`
(6 violations) and `Root.pause` (2 violations) — the only categories
that could plausibly be real, both checked below.

## Three-field check per effect category

### Category A — modifier names as effects (66 / 87 leads = **76%**)

`Auth.auth`, `ERC20.auth`, `Gateway.pauseable`.

Sample: lead `PauseAdmin.pause` — claimed rule "reaching `Auth.auth`
requires modifier `auth`". The "effect" IS the modifier. Reading source
(`src/admins/PauseAdmin.sol`): `pause()` carries the `auth` modifier; the
edge `PauseAdmin.pause → Auth.auth` exists in the graph because every
function with the `auth` modifier emits an outgoing edge to the modifier.

Three-field verdict:
- Host: ✓ exists
- Claimed rule: ✗ — the rule is tautological ("reaching the modifier
  requires the modifier"); not a real protocol invariant
- Unguarded path: technically present in graph but means nothing

**All 66 leads in this category: SPURIOUS, same root cause.**

Root-cause in code (`protocol_rules.py`):
```python
def _is_meaningful_effect(callee, modifiers, internal_nodes):
    if not callee or callee in modifiers:   # ← bare-name check
        return False
```
The check `callee in modifiers` catches `auth` but not `Auth.auth`. The
tonight's whole-program-graph hardening qualified callees to
`Contract.modifier`, defeating the filter.

### Category B — pure library functions as effects (14 / 87 leads = **16%**)

`MathLib.mulDiv` (9), `BytesLib.slice` (4), `BytesLib.toUint8` (1).
Raw-level adds `SafeTransferLib.safeTransferFrom` (6) and
`Messages.messageType` (3).

Sample: lead `InvestmentManager.previewDeposit` — claimed rule "reaching
`MathLib.mulDiv` requires `onlyGateway`". Reading source
(`src/util/MathLib.sol`): `mulDiv` is a `pure` function — fixed-point
arithmetic; no state, no privilege. The protocol calls it everywhere.

Three-field verdict:
- Host: ✓ exists (`previewDeposit` is a view function)
- Claimed rule: ✗ — `mulDiv` is pure math, never a "protected effect"
- Unguarded path: present in graph but meaningless

**All 14 leads in this category: SPURIOUS, same root cause.**

Root cause: library callees enter `internal_nodes` via
`_adjacency`:
```python
if callee and not e.get("external", False):
    internal.add(callee)
```
Slither's `internal_calls` includes calls into `LibraryName.fn()` as
internal edges. So library helpers get treated as internal protocol nodes
and pass the effect filter. The filter has no notion of library-call
exclusion.

### Category C — `low_level_call` sentinel as effect (7 / 87 leads = **8%**)

Bare string used as a placeholder in the call graph for low-level calls
(`.call`, `.delegatecall`, `.staticcall`).

Sample: lead `ERC20.permit` — claimed rule "reaching `low_level_call`
requires modifier `onlyGateway`", guarded by `Escrow.approve` (which
internally hits a low-level call somewhere on its path).

Three-field verdict:
- Host: ✓ exists
- Claimed rule: ✗ — `low_level_call` is a sentinel, not a function; the
  "rule" pairs unrelated paths that happen to perform any low-level call
- Unguarded path: ✗ (not a path to a real privileged effect)

**All 7 leads in this category: SPURIOUS, same root cause.**

Root cause: `_NOISE_EXACT` in `protocol_rules.py` does not include
`low_level_call`. (Seer's own `_CALLEE_NOISE` does — but that's a
different filter on a different code path.)

### Category D — phantom rules from multiple-authorized-paths (0 leads in 87, but 2 in raw 145)

`Root.pause` (2 raw violations, deduped out of the 87 leads).

Sample: raw violation `DelayedAdmin.pause → Root.pause` (claim: missing
`canPause`; guarded sibling: `PauseAdmin.pause`). And the symmetric:
`PauseAdmin.pause → Root.pause` (claim: missing `auth`; guarded sibling:
`DelayedAdmin.pause`).

Reading source:
- `src/admins/DelayedAdmin.sol::pause()` carries `auth` modifier.
- `src/admins/PauseAdmin.sol::pause()` carries `canPause` modifier.
- Both legitimately call `Root.pause()`. Protocol design: two
  intentionally-different-but-both-authorized paths.

Three-field verdict:
- Host: ✓ exists, both
- Claimed rule: ✗ — the "asymmetry" is by design, not a violation; the
  protocol's authorization scheme is "DelayedAdmin OR PauseAdmin", and
  the extractor's `all-guards-required` model can't represent it
- Unguarded path: technically each one is "unguarded" with respect to
  the other's modifier, but both are guarded with their own

**SPURIOUS** — this is a structural limitation of the rule model, not a
filter bug. The fix is a deeper extractor change ("either-of-N-guards is
acceptable") and is **out of scope** for the minimum-filter call. Flag it
as a separate item.

## Aggregate verdict

| | Count | % |
|---|---:|---:|
| REAL leads (genuine claimed-rule violations) | **0** | 0% |
| SPURIOUS leads | **87** | 100% |

By the (a)/(b)/(c) framing: the answer is **(b), with one nuance**. The
population is homogeneous-spurious — no signal hidden in the 87 — and
the over-pairing is mechanical and traceable. The nuance: there are
**four distinct root causes**, three filterable with bare-name additions
and one (the `all-guards-required` model) deeper. The deeper one is not
in the 87 leads (it dedupes out) but appears in the raw violations and
will resurface as the other three are fixed.

The test's premise ("Centrifuge's structural leads were ALL design-
permissionless false positives") is still correct on the SUBSTANTIVE
question — the hardened graph did not expose any genuine claimed-rule
violation it missed before. It just exposed more flavors of false
positive than the old filters anticipated.

## Filter-shape recommendation (NOT a fix — for review)

The minimum filter to bring precision back within budget would be:

1. **Strip contract prefix when checking modifier membership.**
   `_is_meaningful_effect`: also check `bare in modifiers` for qualified
   callees, not just `callee in modifiers`. Kills category A (76% of
   leads).

2. **Mark library-defined callees as non-effects.** Either: (a) annotate
   library calls in the call graph emitter (slither already knows which
   contracts are libraries via `contract.contract_kind`), and exclude
   them from `internal_nodes`; or (b) extend `_NOISE_NAME` regex / a new
   `_LIBRARY_PATHS` set to drop `MathLib.*`, `BytesLib.*`,
   `SafeTransferLib.*`, `Messages.messageType`. Option (a) is structurally
   sounder; (b) is the smaller change. Kills category B (~16%) +
   `SafeTransferLib`/`Messages.messageType` from raw.

3. **Add `low_level_call` to `_NOISE_EXACT`** in `protocol_rules.py`.
   Trivial; kills category C (8%).

After (1)+(2)+(3): expected 87 → 0 spurious of these categories. Category
D (multiple-authorized-paths) will then become visible as the dominant
remaining false-positive shape, and is its own session.

**Acceptance condition for the eventual fix** (per scope contract clause 5):
must preserve the Decent M-03 lead (`UTB.receiveFromBridge` →
`_swapAndExecute` bypassing `retrieveAndCollectFees`). This is the only
true positive the substrate produces; the filter must not remove it.
Easy check: re-run the protocol_aware test on Decent and confirm
`UTB.receiveFromBridge` remains in the lead set.

## What this changes about the Sequence read

The 87→<15 precision regression is mechanical, traceable, and fixable
with three filter additions. The fix is small. Once it lands and Decent
M-03 is preserved, the Sequence run goes on a substrate whose protocol-
aware precision is back within its specified bound.

The Centrifuge surfacing/leads numbers from the 2026-06-30 audit FREEZE
(`m6_backtest_2026-06-30_audited.json`) **are not affected by this
regression**: the BlindRunner uses Seer's path-finding, not the
protocol-aware hypothesis engine. The audited floor (surfacing 2/3,
leads 0/3, gate-confirmed 0 on Centrifuge in-lane) stands as-is.

## Stop point

This session ends with the table above. No filter implementation, no
test relaxation. Bring this to Kyle for review; the filter goes in next
session, on a fix shape signed off on by him, with the Decent M-03
acceptance check baked in.
