"""Recall validation: do M0's tagged surfaces cover the judged Decent findings?

Recall at the entry point is the system's discovery ceiling — the one error
class the verify gate can never recover (a missed function yields no verdict,
just silence). This script checks that every function hosting a published
Code4rena 2024-01-decent High/Medium now appears on M0's verification surface,
and by which signal (structural / keyword / high), across the two in-scope
foundry projects (src/ and lib/decent-bridge).

Usage:
    python tools/validate_recall.py examples/2024-01-decent.model.json \
        examples/2024-01-decent-bridge.model.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Judged findings -> the function(s) that host them. Hosts are (contract, fn);
# a finding is covered if ANY host is on the tagged surface. Mappings are read
# from the public report (code-423n4/2024-01-decent-findings/report.md).
FINDINGS = [
    ("H-01", "DcntEth router settable by anyone (#721)",
     [("DcntEth", "setRouter")]),
    ("H-02", "Missing min-gas check through LayerZero (#525)",
     [("DecentEthRouter", "bridge"), ("DecentEthRouter", "bridgeWithPayload"),
      ("DecentEthRouter", "estimateSendAndCallFee")]),
    ("H-03", "DecentBridgeExecutor.execute misroutes funds on failure (#436)",
     [("DecentBridgeExecutor", "execute")]),
    ("H-04", "Lost tx if dst router lacks WETH reserves (#59)",
     [("DecentEthRouter", "onOFTReceived"), ("DecentEthRouter", "redeemWeth")]),
    ("M-01", "Permanent token loss if swap data outdated (#665)",
     [("UniSwapper", "swapExactIn"), ("UniSwapper", "swapExactOut"),
      ("UniSwapper", "swapNoPath")]),
    ("M-02", "bridgeWithPayload directly callable, fee bypass (#647)",
     [("DecentEthRouter", "bridgeWithPayload")]),
    ("M-03", "UTB.receiveFromBridge bypasses fee/sig verification (#590)",
     [("UTB", "receiveFromBridge")]),
    ("M-04", "Capital loss from fixed fee calculations (#520)",
     [("DecentEthRouter", "bridge"), ("DecentEthRouter", "bridgeWithPayload")]),
    ("M-05", "Refunded ETH stuck in DecentBridgeAdapter (#262)",
     [("DecentEthRouter", "bridgeWithPayload"), ("DecentEthRouter", "bridge")]),
]


def load_surface(model_paths: list[str]) -> dict[tuple[str, str], dict]:
    surface: dict[tuple[str, str], dict] = {}
    for p in model_paths:
        d = json.loads(Path(p).read_text())
        for f in d["verification_surface"]:
            surface[(f["contract"], f["name"])] = f
    return surface


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    surface = load_surface(argv)

    print("M0 recall vs judged Code4rena 2024-01-decent findings")
    print(f"(surface loaded from {len(argv)} model(s); "
          f"{len(surface)} tagged functions)\n")
    covered = 0
    for fid, title, hosts in FINDINGS:
        hit = None
        for host in hosts:
            if host in surface:
                hit = (host, surface[host])
                break
        if hit:
            covered += 1
            (c, fn), info = hit
            sigs = ",".join(info["surfaces"])
            print(f"  [COVERED] {fid}: {c}.{fn}  ({info['confidence']}: {sigs})")
        else:
            shown = ", ".join(f"{c}.{fn}" for c, fn in hosts)
            print(f"  [MISSING] {fid}: none of [{shown}] on surface")
        print(f"            {title}")
    print(f"\nrecall: {covered}/{len(FINDINGS)} judged findings have their host "
          f"function on the tagged surface.")
    return 0 if covered == len(FINDINGS) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
