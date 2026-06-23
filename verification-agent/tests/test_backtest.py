"""Offline tests for M6 backtest — the scorecard must obey its own frozen rules.

No network/forge. These tests pin the taxonomy (a found path without a verdict is
NOT a catch), prove the scorer applies it mechanically over synthetic run dicts,
and check the lane discipline (out-of-lane findings excluded from recall). The
whole point of M6 is a number nobody can move after the fact — so the tests guard
the definitions, not a particular result.
"""

import json
from pathlib import Path

from verification_agent.backtest import (
    ANSWER_KEYS,
    CONTESTS,
    Tier,
    aggregate,
    classify,
    in_lane,
    score_contest,
)
from verification_agent.backtest.tiers import FROZEN_RULES

ROOT = Path(__file__).resolve().parents[1]


# --- the frozen taxonomy ----------------------------------------------------

def test_classify_tier1_requires_gate_confirmed_not_just_a_path():
    # The load-bearing rule: a found path that the gate did NOT confirm is not a
    # catch. `classify` has no `path_found` parameter by design.
    assert classify(surfaced=True, gate_confirmed=False, poc_synthesized=False) is Tier.TIER3
    assert classify(surfaced=True, gate_confirmed=True, poc_synthesized=False) is Tier.TIER1


def test_classify_tier2_requires_poc_synthesis():
    assert classify(surfaced=True, gate_confirmed=True, poc_synthesized=True) is Tier.TIER2


def test_classify_missed_when_not_surfaced():
    assert classify(surfaced=False, gate_confirmed=False, poc_synthesized=False) is Tier.MISSED


def test_gate_confirmed_outranks_surface_flag():
    # Even if the surface flag is absent, a real gate verdict still counts: the
    # verdict is the source of truth, surface tagging is only the recall floor.
    assert classify(surfaced=False, gate_confirmed=True, poc_synthesized=False) is Tier.TIER1


def test_frozen_rules_present():
    for k in ("tier1_requires_gate_confirmed", "tier2_requires_poc_synthesis",
              "path_found_is_not_a_catch", "tiers_never_collapsed"):
        assert FROZEN_RULES[k] is True


# --- the scorer over synthetic (blind) runs ---------------------------------

def _key():
    return [
        ("X-01", "host surfaced + gate confirmed", "access-control", "High",
         ["A.confirmed"]),
        ("X-02", "host surfaced, path found, NO verdict", "access-control", "Medium",
         ["A.leadOnly"]),
        ("X-03", "host surfaced, nothing else", "reachability", "Medium",
         ["A.justSurfaced"]),
        ("X-04", "not surfaced at all", "access-control", "Medium",
         ["A.invisible"]),
        ("X-05", "out of lane, surfaced", "rounding", "Medium",
         ["A.roundingThing"]),
    ]


def _run():
    return {
        "contest_id": "synthetic",
        "blind": True,
        "surfaced_functions": ["A.confirmed", "A.leadOnly", "A.justSurfaced",
                               "A.roundingThing"],
        "found_paths": [
            {"attack_entrypoint": "confirmed", "guard_bypassed": "g"},
            {"attack_entrypoint": "leadOnly", "guard_bypassed": "g"},
        ],
        "gate_confirmed": [
            {"attack_entrypoint": "confirmed", "verdict": "CONFIRMED",
             "poc_synthesized": False},
        ],
    }


def test_scorer_assigns_tiers_mechanically():
    scored = score_contest(_run(), _key())
    by_id = {f["id"]: f for f in scored["findings"]}
    assert by_id["X-01"]["tier"] == Tier.TIER1.value
    # path found but no verdict -> TIER3, and flagged as a lead, never a catch
    assert by_id["X-02"]["tier"] == Tier.TIER3.value
    assert by_id["X-02"]["path_found"] is True
    assert by_id["X-03"]["tier"] == Tier.TIER3.value
    assert by_id["X-04"]["tier"] == Tier.MISSED.value


def test_aggregate_recall_uses_lane_denominator_only():
    scored = score_contest(_run(), _key())
    agg = aggregate([scored])
    # 4 in-lane findings (X-05 rounding excluded). 1 Tier-1 of 4 = 0.25.
    assert agg["in_lane_findings"] == 4
    assert agg["tier1_autonomous_path_and_verdict"]["count"] == 1
    assert agg["tier1_autonomous_path_and_verdict"]["recall"] == 0.25
    assert agg["tier1_autonomous_path_and_verdict"]["ids"] == ["X-01"]
    # surfaced-in-principle: X-01, X-02, X-03 = 3/4
    assert agg["surfaced_total"]["count"] == 3
    # the lead (X-02) is counted but explicitly not a catch
    assert agg["path_found_leads_on_findings"]["count"] == 2
    assert "NOT a catch" in agg["path_found_leads_on_findings"]["note"]


def test_tier2_never_collapsed_into_tier1():
    key = [("P-01", "poc", "access-control", "High", ["A.f"])]
    run = {
        "contest_id": "s", "blind": True,
        "surfaced_functions": ["A.f"], "found_paths": [],
        "gate_confirmed": [{"attack_entrypoint": "f", "verdict": "CONFIRMED",
                            "poc_synthesized": True}],
    }
    agg = aggregate([score_contest(run, key)])
    assert agg["tier2_fully_autonomous"]["count"] == 1
    assert agg["tier1_autonomous_path_and_verdict"]["count"] == 0


# --- lane + registry sanity -------------------------------------------------

def test_in_lane_matches_registry_mechanisms():
    assert in_lane("access-control")
    assert in_lane("signature-verification")
    assert not in_lane("rounding")
    assert not in_lane("dos")


def test_answer_keys_cover_registered_contests():
    for c in CONTESTS:
        assert c["id"] in ANSWER_KEYS
        assert ANSWER_KEYS[c["id"]], f"empty answer key for {c['id']}"


def test_decent_is_calibration_centrifuge_is_blind():
    by_id = {c["id"]: c for c in CONTESTS}
    assert by_id["2024-01-decent"]["blind"] is False
    assert by_id["2023-09-centrifuge"]["blind"] is True
