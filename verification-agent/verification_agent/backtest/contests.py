"""Contest registry + answer keys for the backtest.

LANE DISCIPLINE: the set is curated to the mechanisms Seer/the gate actually
reach today — access-control / cross-domain / reachability / signature — not
padded with rounding/DoS/accounting contests that would measure the gap rather
than the capability.

BLIND DISCIPLINE: the runner uses only the `models`/`repo_local` fields. The
`ANSWER_KEYS` below are opened ONLY by the scorer, after the run is frozen.
Decent was authored answer-key-informed (it is the calibration contest, M-03 was
known); Centrifuge's loop ran on code alone before these findings were read
(`blind: True`).

Lane classification is by mechanism: in-lane = access-control / cross-domain-auth
/ signature-verification / reachability / replay / proof-forgery. Out-of-lane =
fund-routing / rounding / gas / dos / accounting / swap-correctness — measured
but excluded from the lane recall denominator.

State label: IMPLEMENTED.
"""

from __future__ import annotations

_LANE_MECHANISMS = {
    "access-control", "cross-domain-auth", "signature-verification",
    "reachability", "replay", "proof-forgery", "message-boundary",
}


def in_lane(mechanism: str) -> bool:
    return mechanism in _LANE_MECHANISMS


# Filled by the harness at run time (paths resolved relative to the examples dir
# and the local clones). Kept as ids here; the CLI wires the concrete paths.
CONTESTS = [
    {
        "id": "2024-01-decent",
        "blind": False,   # calibration: M-03 was known when the gate case was built
        "models": ["2024-01-decent.model.json", "2024-01-decent-bridge.model.json"],
        "lane": "cross-chain / access-control",
    },
    {
        "id": "2023-09-centrifuge",
        "blind": True,    # loop ran on code alone before findings were read
        "models": ["2023-09-centrifuge.model.json"],
        "lane": "cross-chain / access-control / signature",
    },
]

# (id, title, mechanism, severity, hosts[, void_info]). hosts = candidate host
# functions; the finding is "surfaced" if ANY host is on the model's verification
# surface. An optional 6th element {"voided": True, "reason": "..."} marks rows
# that fail the three-field verification (host / bug class / adversary-exists)
# against the actual C4 issue — those rows are excluded from the in-lane
# denominator and called out in the FREEZE artifact, rather than silently
# inflating or deflating recall while the key is being re-audited.
ANSWER_KEYS = {
    "2024-01-decent": [
        ("H-01", "DcntEth router settable by anyone", "access-control", "High",
         ["DcntEth.setRouter"]),
        ("H-02", "Missing min-gas check through LayerZero", "gas", "High",
         ["DecentEthRouter.bridge"]),
        ("H-03", "DecentBridgeExecutor.execute misroutes funds on failure", "fund-routing", "High",
         ["DecentBridgeExecutor.execute"]),
        ("H-04", "Lost tx if dst router lacks WETH reserves", "liquidity", "High",
         ["DecentEthRouter.onOFTReceived"]),
        ("M-01", "Permanent token loss if swap data outdated", "swap-correctness", "Medium",
         ["UniSwapper.swapExactIn"]),
        ("M-02", "bridgeWithPayload directly callable, fee bypass", "access-control", "Medium",
         ["DecentEthRouter.bridgeWithPayload"]),
        ("M-03", "UTB.receiveFromBridge bypasses fee/sig verification", "access-control", "Medium",
         ["UTB.receiveFromBridge"]),
        ("M-04", "Capital loss from fixed fee calculations", "accounting", "Medium",
         ["DecentEthRouter.bridge"]),
        ("M-05", "Refunded ETH stuck in DecentBridgeAdapter", "fund-routing", "Medium",
         ["DecentEthRouter.bridgeWithPayload"]),
    ],
    "2023-09-centrifuge": [
        ("M-01", "onlyCentrifugeChainOrigin can't require msg.sender == axelarGateway",
         "cross-domain-auth", "Medium", ["Gateway.handle"],
         {"voided": True,
          "reason": ("answer-key mis-keyed: C4 #537 places the finding in "
                     "AxelarRouter.execute (modifier onlyCentrifugeChainOrigin), "
                     "and the mechanism is denial-of-service (msg.sender == "
                     "axelarGateway can never hold under real Axelar flow), not "
                     "access-control bypass. Gateway.handle is guarded by a "
                     "different modifier (onlyIncomingRouter) and is not the "
                     "vulnerable function. Re-audit pending; row excluded from "
                     "in-lane denominator so a substrate hit on Gateway.handle "
                     "cannot score against this finding.")}),
        ("M-02", "requestRedeemWithPermit front-run with different liquidity pool",
         "signature-verification", "Medium", ["LiquidityPool.requestRedeemWithPermit"]),
        # M-03 voided 2026-06-30: published mechanism (C4 #146) is "permit() always
        # reverts on tranche tokens because cached DOMAIN_SEPARATOR is computed
        # with empty name". Pure liveness — no adversary, no privileged effect
        # reached. Same shape as M-01: gate cannot adjudicate honest-path-broken.
        ("M-03", "Cached DOMAIN_SEPARATOR incorrect for tranche tokens (permit)",
         "signature-verification", "Medium",
         ["LiquidityPool.requestDepositWithPermit", "ERC20.permit"],
         {"voided": True,
          "reason": ("re-audit (2026-06-30): C4 #146 mechanism is 'permit() "
                     "always reverts for tranche tokens because the cached "
                     "DOMAIN_SEPARATOR is computed with empty name'. Pure "
                     "liveness / DoS for legitimate permit integrations, no "
                     "adversary. Fails three-field check on adversary-exists, "
                     "same shape as M-01. See docs/NEXT_SESSION_KEY_REAUDIT.md.")}),
        # M-04 re-keyed 2026-06-30: C4 #143's first line is "Deposit and mint
        # under LiquidityPool lack access control"; the DoS is the IMPACT,
        # missing-access-control is the MECHANISM. Adversary exists (attacker
        # DoSes a victim). The finding's recommendation is literally "Have some
        # access control modifiers like withApproval". In-lane access-control.
        ("M-04", "Deposit tiny amount to DoS other users (lack of access control on receiver)",
         "access-control", "Medium",
         ["LiquidityPool.deposit", "LiquidityPool.mint"]),
        ("M-05", "maxDeposit claiming blocks other users", "accounting", "Medium",
         ["LiquidityPool.deposit"]),
        # M-06 voided 2026-06-30: C4 #92's bug is "DelayedAdmin's implementation
        # doesn't include a function to call PauseAdmin.removePauser, which the
        # README spec says it should". This is missing capability / spec-conformance
        # — there is no adversary and no privileged-effect-reached-without-guard.
        # The previous session's leading gate-generalization candidate; killed by
        # the re-audit on mechanism and adversary-exists fields.
        ("M-06", "DelayedAdmin cannot PauseAdmin.removePauser", "access-control", "Medium",
         ["PauseAdmin.removePauser", "DelayedAdmin.removePauser"],
         {"voided": True,
          "reason": ("re-audit (2026-06-30): C4 #92 is 'DelayedAdmin lacks a "
                     "function its README spec promises (removePauser caller)'. "
                     "Missing capability / spec-conformance bug, NOT access-control "
                     "bypass. No adversary; no privileged effect reached. Fails "
                     "three-field check on mechanism and adversary-exists. KILLS "
                     "the prior session's leading gate-generalization target.")}),
        ("M-07", "trancheTokenAmount should round up on withdrawal", "rounding", "Medium",
         ["LiquidityPool.withdraw"]),
        # M-08: hosts tightened 2026-06-30 — RestrictionManager.member is a view
        # getter the bug *uses*, not the vulnerable function. The bug lives in
        # detectTransferRestriction, which checks only the receiver's membership
        # and lets a blacklisted sender bypass the restriction. Mechanism + host
        # + adversary all check out for the remaining host.
        ("M-08", "RestrictionManager incompletely implements ERC1404",
         "access-control", "Medium",
         ["RestrictionManager.detectTransferRestriction"]),
    ],
}
