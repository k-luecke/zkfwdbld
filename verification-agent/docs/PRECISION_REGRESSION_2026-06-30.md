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

## Full-trace verification (not name-resemblance)

The classification above is by *effect category*. The categories are
structural buckets, and "the effect is a modifier so it's spurious" is
itself the name-resemblance shortcut the answer-key audit just taught us
to mistrust. So one full-trace read per bucket, to source — host found,
path checked, claimed rule shown not to exist as a protocol invariant
rather than just looking wrong on its name.

### Category A trace — `PauseAdmin.pause → Auth.auth` (modifier-as-effect)

- **Host in source**: `src/admins/PauseAdmin.sol` line 47:
  `function pause() public canPause`. Externally callable. ✓
- **Path in source**: `PauseAdmin.pause()` body is one line: `root.pause()`.
  Edge chain in the model: `PauseAdmin.pause → Root.pause` (external, real
  call), then `Root.pause → Auth.auth` (synthetic modifier edge because
  `Root.pause` carries the `auth` modifier). So the depth-2 transitive
  reach `PauseAdmin.pause ⤳ Auth.auth` is real in the graph, but the
  terminal edge is the synthetic modifier-as-callee artifact, not a
  function call. There is no actual call from `pause()` to anything named
  `auth` in source.
- **Claimed rule in source**: "reaching `Auth.auth` requires the `auth`
  modifier." The extractor inferred this rule by observing 47 edges of
  the form `<auth-carrying function> → Auth.auth` (every `auth`-modified
  function emits this synthetic edge). It then sees `PauseAdmin.pause`
  transitively reach `Auth.auth` through the legitimately-authorized
  `Root.pause` intermediate, and flags it because `pause()` itself
  doesn't carry `auth` (it carries `canPause`). There is no such protocol
  invariant — the protocol's intended scheme is "Root.pause is callable
  by `auth`-wards directly OR via `canPause`-protected `PauseAdmin.pause`",
  a legitimate dual-path design.

**Verdict: SPURIOUS confirmed by source.** Two compounding errors: (i)
`Auth.auth` exists as a graph node only because of synthetic
modifier-as-callee edges (the qualified-name filter miss), and (ii) the
transitive reach goes through an intermediate (`Root.pause`) that IS
legitimately authorized via a different scheme — the bleed-through from
the category-D "multiple-authorized-paths" shape. The qualified-modifier
filter alone resolves (i); (ii) is fully resolved only when the rule
model also handles "either-of-N-guards" (category D, deferred).

### Category B trace — `InvestmentManager.previewDeposit → MathLib.mulDiv` (library-as-effect)

- **Host in source**: `src/InvestmentManager.sol` line 370,
  `function previewDeposit(address user, address liquidityPool, uint256 _currencyAmount)`.
  Public view function. ✓
- **Path in source**: `previewDeposit` calls `calculateDepositPrice`
  which calls `_calculatePrice` which calls `MathLib.mulDiv`. So the
  path to `mulDiv` is real. ✓
- **Claimed rule in source**: "reaching `MathLib.mulDiv` requires
  `onlyGateway`" — read `MathLib.sol` directly: `function mulDiv(uint256
  x, uint256 y, uint256 denominator) internal pure returns (uint256
  result)`. It's `internal pure` — stateless math borrowed from
  OpenZeppelin's Math.sol via the contract's own header comment. There
  is **no protocol invariant** stating "mulDiv must be gated by
  onlyGateway" — many code paths call mulDiv for many unrelated reasons
  (deposit, redeem, withdraw, price preview). The "asymmetry" is
  coincidence of shared library use, not a stated rule.

**Verdict: SPURIOUS confirmed by source.** The path exists, but the
effect is a pure utility function the protocol calls from many
intentionally-unrelated contexts; no invariant gates it.

### Category C trace — `ERC20.permit → low_level_call` (sentinel-as-effect)

- **Host in source**: `src/token/ERC20.sol` line 225,
  `function permit(...) external`. Externally callable. ✓
- **Path in source**: `permit()` performs an `ecrecover` and a state
  write (`allowance[owner][spender] = value`). It does NOT call
  `.call`/`.delegatecall`/`.staticcall` directly. The edge to
  `low_level_call` in the call graph comes from a transitive reach
  through some downstream path (slither's `_reach(adj, "ERC20.permit",
  depth=5)` lands on a function that does a low-level call somewhere).
- **Claimed rule in source**: "reaching `low_level_call` requires
  `auth`" — `low_level_call` is not a function; it's the literal string
  `slither_runner.py` emits as a callee placeholder when a function has
  a low-level call (`out.append(CallEdge(caller=caller, callee="low_level_call", external=True))`).
  The "rule" pairs any two paths that happen to transitively reach any
  low-level call, of which there are many.

**Verdict: SPURIOUS confirmed by source.** The "effect" is a sentinel
string, not a function — by construction it cannot be a real protocol
invariant.

### What the traces add to the bucket diagnosis

The buckets are right *because of the mechanism in each case*, not
because of name resemblance:
- Category A: the rule is tautological by emission (modifier reaches
  itself).
- Category B: the rule pairs intentionally-unrelated paths through a
  pure library.
- Category C: the "effect" is a placeholder string.

In none of the three cases would reading more leads in the same bucket
change the verdict, because the spurious-ness lives in the
graph-construction logic, not in any individual lead. Reading more leads
in *other* buckets would be the move that could change the verdict —
but there are no other buckets in the 87.

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

## Stop point (original)

This session originally ended at characterization — the table above —
with no filter implementation. After review, Kyle endorsed (1) + (2a) +
(3) with Decent M-03 as the acceptance gate. The fix was then
implemented in the same session.

## Post-fix outcome

The three-part minimum filter landed (commits in this push):

* **(1) Qualified-modifier strip** — `_is_meaningful_effect` now strips
  the `Contract.` prefix when checking modifier membership.
* **(2a) Structural library marking** — `CallEdge.library_callee` field
  populated at emission time from `slither.contract.is_library`;
  `_adjacency` excludes library callees from `internal_nodes`. Plus a
  follow-up that was forced by the data: library functions themselves
  emit synthetic self-recursive edges that put them into `internal_nodes`
  as *callers*, defeating the per-callee flag — so the slither_runner
  now also **skips emitting outgoing edges from library bodies**.
  Nothing inside a library is privileged or attacker-reachable, so
  tracing through them is pure noise; their callers are still emitted
  via the high-level-call edge from non-library code.
* **(3)** `low_level_call` added to `_NOISE_EXACT`.

Centrifuge protocol-aware leads: **87 → 2**. Budget < 15: ✓ under.
The 2 remaining leads are exactly the pre-registered Root.pause
category-D shape (multi-authorized-paths), documented at
`docs/SEQUENCE_PRE_REGISTRATION.md` as a known confound on Sequence
output.

Decent acceptance gate: **✓ M-03 lead preserved**
(`UTB.receiveFromBridge` with `claimed-rule-violation` /
`retrieveAndCollectFees`). Decent total protocol-aware leads: 5
(sharpening, not regression).

End-to-end backtest scorecard against the audited key: **unchanged**
from the audit-only FREEZE. TIER-1 = 1, surfaced = 5, recall = 0.833,
Seer leads on findings = 1. The fix did precisely what it was supposed
to and **did not move the floor** — the BlindRunner uses Seer's
path-finder, not the protocol-aware hypothesis engine, and the fix is
on the latter.

xfail marker removed; test now passes naturally. Suite: 80 / 80.

## What's left in the "things known broken on the substrate Sequence
runs on" list

**Empty.** The Root.pause / OR-authorized-path shape is pre-registered
and readable, not broken. After this fix, the next instruction is the
blind run-book for Sequence, not another hardening pass.
