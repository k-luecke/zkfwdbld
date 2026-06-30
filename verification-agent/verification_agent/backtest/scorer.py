"""Backtest scorer — opens the answer keys and applies the FROZEN taxonomy.

Run only AFTER the blind run is frozen. Tier assignment is mechanical
(tiers.classify); this module just gathers the booleans (surfaced / path-found /
gate-confirmed) by comparing the frozen run against the answer key, and tallies.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from typing import Any

from .contests import in_lane
from .tiers import FROZEN_RULES, Tier, classify

# Guard: if a future edit weakens the taxonomy, fail loudly rather than inflate.
assert FROZEN_RULES["tier1_requires_gate_confirmed"]
assert FROZEN_RULES["path_found_is_not_a_catch"]


def _qualified(record: dict[str, Any]) -> str:
    """Best-effort fully-qualified ``Contract.function`` id for a run record.

    Prefer an explicit ``attack_target`` (already qualified); else combine the
    contract from the hypothesis ``target`` with the bare ``attack_entrypoint``.
    Comparing on the qualified id is what prevents over-crediting a finding to the
    wrong contract when a function name repeats (Gateway.handle vs Router.handle).
    """
    t = record.get("attack_target")
    if t and "." in t:
        return t
    target = record.get("target", "") or ""
    contract = target.split(".")[0] if "." in target else ""
    fn = record.get("attack_entrypoint") or ""
    return f"{contract}.{fn}" if contract else fn


def score_contest(run: dict[str, Any], answer_key: list[tuple]) -> dict[str, Any]:
    surfaced_set = set(run.get("surfaced_functions", []))
    confirmed_fns = {
        _qualified(c) for c in run.get("gate_confirmed", [])
        if c.get("verdict") == "CONFIRMED"}
    confirmed_poc = {
        _qualified(c) for c in run.get("gate_confirmed", [])
        if c.get("verdict") == "CONFIRMED" and c.get("poc_synthesized")}
    lead_fns = {_qualified(p) for p in run.get("found_paths", [])}

    findings = []
    for fid, title, mechanism, severity, hosts in answer_key:
        # Answer-key hosts are already fully qualified (e.g. UTB.receiveFromBridge);
        # compare qualified-to-qualified everywhere so a function name repeated
        # across contracts cannot be cross-credited.
        host_set = set(hosts)
        surfaced = bool(host_set & surfaced_set)
        gate_confirmed = bool(host_set & confirmed_fns)
        poc = bool(host_set & confirmed_poc)
        path_found = bool(host_set & lead_fns)
        tier = classify(surfaced=surfaced, gate_confirmed=gate_confirmed,
                        poc_synthesized=poc)
        findings.append({
            "id": fid, "title": title, "mechanism": mechanism, "severity": severity,
            "in_lane": in_lane(mechanism),
            "surfaced": surfaced, "path_found": path_found,
            "gate_confirmed": gate_confirmed, "tier": tier.value,
        })
    return {"contest_id": run["contest_id"], "blind": run.get("blind"),
            "findings": findings,
            "leads": sorted(lead_fns),
            "n_surface_flagged": len(surfaced_set)}


def aggregate(scored: list[dict[str, Any]]) -> dict[str, Any]:
    lane = [f for s in scored for f in s["findings"] if f["in_lane"]]
    n = len(lane) or 1
    surfaced = [f for f in lane if f["surfaced"]]
    tier1 = [f for f in lane if f["tier"] == Tier.TIER1.value]
    tier2 = [f for f in lane if f["tier"] == Tier.TIER2.value]
    tier3 = [f for f in lane if f["tier"] == Tier.TIER3.value]
    path_leads = [f for f in lane if f["path_found"]]
    return {
        "frozen_taxonomy": True,
        "in_lane_findings": len(lane),
        "tier1_autonomous_path_and_verdict": {"count": len(tier1),
                                              "recall": round(len(tier1) / n, 3),
                                              "ids": [f"{f['id']}" for f in tier1]},
        "tier2_fully_autonomous": {"count": len(tier2), "recall": round(len(tier2) / n, 3)},
        "tier3_surfaced_not_caught": {"count": len(tier3)},
        "surfaced_total": {"count": len(surfaced),
                           "recall": round(len(surfaced) / n, 3)},
        "path_found_leads_on_findings": {"count": len(path_leads),
                                         "recall": round(len(path_leads) / n, 3),
                                         "note": "a lead is NOT a catch (no verdict)"},
    }
