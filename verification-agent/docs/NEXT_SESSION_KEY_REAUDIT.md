# Next session: full answer-key re-audit

One row of the backtest answer key was found mis-keyed during the (a′)
run on 2026-06-30 — Centrifuge M-01 was attributed to `Gateway.handle`
and labeled `cross-domain-auth` (access-control bypass), but the actual
C4 #537 finding lives in `AxelarRouter.execute` and is a denial-of-service
(`onlyCentrifugeChainOrigin` can never be satisfied by the real Axelar
flow, so legitimate messages always revert; no adversary).

That row is now voided in `backtest/contests.py` (excluded from the
in-lane denominator, surfaced in the FREEZE artifact with provenance).
But one mis-keyed row is a typo; the discipline is checking whether it's
a pattern across the rest of the key. The other in-lane rows have not
had the same C4-issue verification done.

## The three-field protocol

For EACH in-lane row in `ANSWER_KEYS`, verify three fields **independently**
against the published C4 issue (or equivalent source). A key that's been
wrong once hasn't earned the benefit of the doubt on the other two fields
just because the function name looks plausible.

1. **Host function**. The `hosts` list MUST contain the function(s) the
   published finding actually identifies as vulnerable. Compare names
   AND modifier guards against the source at the contest commit. If the
   finding describes "modifier M can be bypassed on function F", confirm
   F carries M (or `M` is the relevant modifier on F's caller).

2. **Bug class**. The `mechanism` field MUST match the published finding's
   actual mechanism — not what the function name suggests. The full set
   accepted in-lane is currently `{access-control, cross-domain-auth,
   signature-verification, reachability, replay, proof-forgery,
   message-boundary}`. If the finding is denial-of-service, accounting,
   rounding, swap-correctness, fund-routing, gas — it is out-of-lane;
   mark it so, do not relabel it.

3. **Adversary exists**. The published mechanism MUST involve an
   adversary reaching a privileged effect through an unauthorized path.
   If the mechanism is "the honest path is broken" (DoS, liveness,
   griefing-by-self), there is no adversary — the gate as currently
   designed cannot adjudicate it, and `surfacing` claims against it are
   structurally meaningless. Mark voided.

If ANY of the three fields fails, the row is voided with a
`{"voided": True, "reason": "..."}` entry. Do NOT silently fix one
field; fix all three or void.

## In-lane rows to re-audit (current state)

### 2024-01-decent (calibration)

Already verified in the 2026-06-29 session (Task 3 / mechanism match):
- **M-03** — host `UTB.receiveFromBridge`, mechanism `access-control`,
  adversary exists. C4 #590. **Verified: pass on all three fields.**

Rows still requiring re-audit (these were in the original key but not
independently field-verified yet):
- **H-01** "DcntEth router settable by anyone" → `DcntEth.setRouter`,
  `access-control`, severity High. C4 #721. Verify.
- **M-02** "bridgeWithPayload directly callable, fee bypass" →
  `DecentEthRouter.bridgeWithPayload`, `access-control`, severity Medium.
  Verify.

### 2023-09-centrifuge (blind)

- **M-01** — **VOIDED** (2026-06-30): host `Gateway.handle`, mechanism
  `cross-domain-auth`. All three fields fail vs C4 #537.
- **M-02** "requestRedeemWithPermit front-run with different liquidity
  pool" → `LiquidityPool.requestRedeemWithPermit`,
  `signature-verification`, severity Medium. Verify.
- **M-03** "Cached DOMAIN_SEPARATOR incorrect for tranche tokens (permit)"
  → `[LiquidityPool.requestDepositWithPermit, ERC20.permit]`,
  `signature-verification`, severity Medium. Verify.
- **M-06** "DelayedAdmin cannot PauseAdmin.removePauser" →
  `[PauseAdmin.removePauser, DelayedAdmin.removePauser]`,
  `access-control`, severity Medium. Verify carefully — this row is the
  most promising target for the next gate-generalization case (option 2
  from the prior session) **if it survives re-audit**.
- **M-08** "RestrictionManager incompletely implements ERC1404" →
  `[RestrictionManager.detectTransferRestriction, RestrictionManager.member]`,
  `access-control`, severity Medium. Verify.

## Workflow

1. For each row above, fetch the corresponding C4 issue
   (`code-423n4/{contest}-findings/issues/N`).
2. Read the published finding's mechanism description in full.
3. Open `src/.../<contract>.sol` at the contest commit and check the
   modifier(s) on the cited host function.
4. Record verdict per row (PASS / VOID + reason).
5. Update `ANSWER_KEYS` in `backtest/contests.py` for any voids.
6. Re-run the backtest. The FREEZE artifact will surface any new voids
   automatically (see CLI: ANSWER-KEY VOIDS section, voided_findings
   field in JSON).
7. Pick the gate-generalization target ONLY from rows that survived
   re-audit. If M-06 survives, it is the leading candidate — clean
   access-control bypass on a well-defined modifier (`auth` in Auth.sol).

## After the re-audit

The verified key is the prerequisite for **either** a sound gate-
generalization case (option 2 from the prior session) **or** the real
**Sequence** run (unseen target, blind, M4.5 synthesizes its own gate
case). The Sequence run is the load-bearing unseen-target verdict and is
still untouched. Do not run it against an un-audited key.
