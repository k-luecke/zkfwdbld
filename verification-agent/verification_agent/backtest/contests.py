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

# (id, title, mechanism, severity, hosts). hosts = candidate host functions; the
# finding is "surfaced" if ANY host is on the model's verification surface.
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
         "cross-domain-auth", "Medium", ["Gateway.handle"]),
        ("M-02", "requestRedeemWithPermit front-run with different liquidity pool",
         "signature-verification", "Medium", ["LiquidityPool.requestRedeemWithPermit"]),
        ("M-03", "Cached DOMAIN_SEPARATOR incorrect for tranche tokens (permit)",
         "signature-verification", "Medium",
         ["LiquidityPool.requestDepositWithPermit", "ERC20.permit"]),
        ("M-04", "Deposit tiny amount to DoS other users", "dos", "Medium",
         ["LiquidityPool.requestDeposit"]),
        ("M-05", "maxDeposit claiming blocks other users", "accounting", "Medium",
         ["LiquidityPool.deposit"]),
        ("M-06", "DelayedAdmin cannot PauseAdmin.removePauser", "access-control", "Medium",
         ["PauseAdmin.removePauser", "DelayedAdmin.removePauser"]),
        ("M-07", "trancheTokenAmount should round up on withdrawal", "rounding", "Medium",
         ["LiquidityPool.withdraw"]),
        ("M-08", "RestrictionManager incompletely implements ERC1404",
         "access-control", "Medium",
         ["RestrictionManager.detectTransferRestriction", "RestrictionManager.member"]),
    ],
}
