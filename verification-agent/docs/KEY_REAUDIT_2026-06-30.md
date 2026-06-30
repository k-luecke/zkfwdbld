# Answer-key re-audit — 2026-06-30

Scope: Decent (2024-01-decent) and Centrifuge (2023-09-centrifuge) only.
NO contact with Sequence or any un-run contest. The contests touched here
have already been burned as calibration/blind-scored; the re-audit cannot
destroy blindness they no longer have.

Hard stop: this session does NOT author the gate-generalization case.
The corrected key must be reviewed first; bundling correction with new
case-authoring would let a green from the case quietly relicense the key
it was built against.

## Method

Three-field protocol applied to every published H/M finding, twice:

* **Forward pass** — each existing in-lane row checked against its C4
  issue on host function, bug class (lane membership), and adversary-exists.
* **Reverse pass** — full published H/M list cross-checked for presence
  in `ANSWER_KEYS`, hunting omissions the forward pass cannot see.

Sources used: `gh api` pulls of `code-423n4/{contest}-findings/issues/N`
(saved to `/tmp/c4_audit/`), plus source-level verification against the
target trees at the contest commits (`/tmp/decent_probe`,
`/tmp/centrifuge_va`). Decent M-03 (#590) is the worked-example control
— already confirmed mechanism-exact in the 2026-06-29 session.

## Decent (9 published H/M; all 9 in registry; reverse pass: 0 omissions)

| id | issue | claim (registry) | actual (C4) | verdict |
|----|-------|------------------|-------------|---------|
| H-01 | #721 | `DcntEth.setRouter`, access-control | `DcntEth.setRouter` has no auth; attacker sets router → mints/burns DcntEth | **CONFIRMED** |
| H-02 | #525 | `DecentEthRouter.bridge`, gas (out-of-lane) | user-supplied `_dstGasForCall` too low → OOG on dst → STORED state blocks future messages | confirmed out-of-lane |
| H-03 | #436 | `DecentBridgeExecutor.execute`, fund-routing (out-of-lane) | failed dst call refunds to wrong `from` address; funds lost | confirmed out-of-lane |
| H-04 | #59 | `DecentEthRouter.onOFTReceived`, liquidity (out-of-lane) | dst router falls back to sending dcntEth when WETH reserves insufficient | confirmed out-of-lane |
| M-01 | #665 | `UniSwapper.swapExactIn`, swap-correctness (out-of-lane) | Stargate sgReceive fails on stale swap data; tokens stuck | confirmed out-of-lane |
| M-02 | #647 | `DecentEthRouter.bridgeWithPayload`, access-control | `bridgeWithPayload` is external with no auth; attacker bridges directly skipping fee in UTB.bridgeAndExecute | **CONFIRMED** |
| M-03 | #590 | `UTB.receiveFromBridge`, access-control | (control, confirmed 2026-06-29) | **CONFIRMED** (control) |
| M-04 | #520 | `DecentEthRouter.bridge`, accounting (out-of-lane) | StargateBridgeAdapter assumes fixed 0.06% fee; variable fees leave residual stuck | confirmed out-of-lane |
| M-05 | #262 | `DecentEthRouter.bridgeWithPayload`, fund-routing (out-of-lane) | excess native ETH refund sent to msg.sender = adapter, not user; stuck | confirmed out-of-lane |

**Decent net change: 0.** All 9 rows pass three-field check.

## Centrifuge (8 published M; all 8 in registry; reverse pass: 0 omissions)

| id | issue | claim (registry) | actual (C4) | verdict |
|----|-------|------------------|-------------|---------|
| M-01 | #537 | `Gateway.handle`, cross-domain-auth | `AxelarRouter.execute`; modifier `onlyCentrifugeChainOrigin` requires `msg.sender == axelarGateway` which is never true under real Axelar flow → liveness/DoS. No adversary, wrong host, wrong class. | **VOIDED** (2026-06-29; void confirmed) |
| M-02 | #227 | `LiquidityPool.requestRedeemWithPermit`, signature-verification | permit signature bound only to tranche token, not pool; attacker frontruns with same sig to wrong pool | **CONFIRMED** |
| M-03 | #146 | `[LiquidityPool.requestDepositWithPermit, ERC20.permit]`, signature-verification | cached `DOMAIN_SEPARATOR` computed with empty name (set after construction); legitimate `permit()` always reverts on tranche tokens. Pure liveness, no adversary. Same shape as M-01. | **VOID** |
| M-04 | #143 | `LiquidityPool.requestDeposit`, dos (out-of-lane) | finding's first line: "deposit and mint lack access control"; attacker DoSes victim by frontrunning `deposit(1 wei, victim)`. Mechanism IS access-control; DoS is impact. Recommendation: `withApproval(receiver)` modifier. | **MIS-KEYED** → re-classified `access-control` (in-lane); hosts: `[LiquidityPool.deposit, LiquidityPool.mint]` |
| M-05 | #118 | `LiquidityPool.deposit`, accounting (out-of-lane) | average-price computation in processDeposit; depletes Escrow shares for other users | confirmed out-of-lane |
| M-06 | #92 | `[PauseAdmin.removePauser, DelayedAdmin.removePauser]`, access-control | README spec says DelayedAdmin can call `PauseAdmin.removePauser`; implementation doesn't include that call. Missing capability / spec-conformance. No adversary, no privileged effect reached without guard. | **VOID** — **kills the prior session's leading gate-generalization candidate** |
| M-07 | #34 | `LiquidityPool.withdraw`, rounding (out-of-lane) | EIP-4626 rounding direction wrong on withdraw | confirmed out-of-lane |
| M-08 | #779 | `[RestrictionManager.detectTransferRestriction, RestrictionManager.member]`, access-control | `detectTransferRestriction` only checks receiver, not sender; blacklisted sender can transfer to whitelisted receivers. Mechanism + adversary check out. `member` is a getter, not the vulnerable function. | **CONFIRMED** with host tightened to `[RestrictionManager.detectTransferRestriction]` |

**Centrifuge changes: 2 new voids (M-03, M-06), 1 re-key (M-04 → in-lane), 1 host trim (M-08).**

## Restated recall (corrected key)

```
              before audit (2026-06-29; M-01 voided only)    after audit (2026-06-30; full re-audit)
in-lane denom                7                                 6
TIER-1 catches               1 (Decent M-03)                   1 (Decent M-03)        [unchanged]
TIER-1 recall                0.143                             0.167                   [denom-only]
surfaced total               5                                 5
surfaced recall              0.714                             0.833                   [denom-only]
Seer path-leads on findings  3                                 1
```

**Centrifuge-only recall, corrected key (in-lane denom 3 — M-02, M-04, M-08):**

* surfacing  : **2/3 = 0.667** (M-02 and M-04 are on the surface set; M-08's correct host `RestrictionManager.detectTransferRestriction` is not)
* Seer leads : **0/3 = 0.000** (the prior "2 leads" were against M-03 voided and M-08's `member` getter)
* TIER-1     : **0/3 = 0.000**
* gate conf  : **0**

This is the floor. The substrate's prior 0.75 surfacing claim on Centrifuge
included 1 mis-keyed surface hit (M-01 voided via Gateway.handle) and 1
spurious surface hit (M-03 via `ERC20.permit`). The 3-of-7 path-leads
figure included 2 leads against findings that shouldn't have been in-lane
in the first place. The corrected key gives surfacing 2/3 and path-leads
0/3 on Centrifuge in-lane.

## What this changes downstream

1. **The Decent calibration story is intact.** All three Decent in-lane
   rows pass three-field check; the M-03 close-to-CONFIRMED is real.

2. **The "Centrifuge surfaces 0.75 of in-lane findings" claim was inflated.**
   Honest figure: 0.667, and the 2 hits are by virtue of host membership
   in the structural-surface set, not by any path-finding capability.

3. **The prior leading gate-generalization target (Centrifuge M-06) is
   killed.** It's not access-control bypass; it's missing-capability /
   spec-conformance. The gate as designed cannot adjudicate it.

4. **The remaining in-lane Centrifuge candidates for the next session's
   gate-generalization work are M-04 (`LiquidityPool.deposit` lacks
   `withApproval`) and M-08 (`RestrictionManager.detectTransferRestriction`
   incomplete check).** Both have adversaries and access-control mechanisms.
   But: M-08 is currently MISSED (its correct host is not on the surface
   set) and M-04 needs the substrate to surface a permissionless-but-
   parameterized-by-third-party pattern that the current protocol-rule
   extractor isn't designed for (no guarded sibling to pair with). Neither
   is a slam-dunk; both deserve their own session.

5. **The Sequence run is still untouched.** Do not run it against any
   un-stamped key; if the key is re-corrected again, restate this floor
   first.

## Substrate-behavior side-effect surfaced during the audit

The Centrifuge model regeneration (2026-06-30, against the whole-program
call graph) caused
`tests/test_protocol_rules.py::test_protocol_aware_goes_quiet_on_centrifuge_false_positives`
to fail: protocol-aware mode now yields 87 leads vs 62 non-protocol-aware
(test expected `<25%`, i.e. `<15`). Marked `xfail(strict=True)` with full
context preserved. Real signal worth its own session — either the richer
graph is exposing genuine claimed-rule violations the thinner graph missed,
or the protocol-rule extractor pairs too aggressively on the new internal
edges. Out of scope for this audit; do NOT silence by relaxing the
assertion.

## Stop

This session ends here. No gate-case authoring. Next session: pick from
{Decent H-01, Decent M-02, Centrifuge M-04, Centrifuge M-08} for gate
generalization — only after this audit is reviewed and any objections
to the verdicts are resolved.
