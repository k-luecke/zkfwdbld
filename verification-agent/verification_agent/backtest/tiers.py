"""FROZEN backtest taxonomy — pinned before any contest is scored.

This is the M6 analog of the predicate-author separation: the definition of what
counts as a "catch" is fixed in code BEFORE the run, so no one can decide after
seeing the results whether a borderline outcome counts. Classification is
mechanical (see `classify`), never post-hoc judgment.

DO NOT relax these definitions to make a number look better. The whole system is
built on verdicts the author can't fake; the scorecard obeys the same rule.

The three tiers are logged SEPARATELY and never collapsed into one headline:

  TIER-1  autonomous path + autonomous verdict
          A backend independently FOUND the path AND the M1 gate CONFIRMED it.
          The scenario harness (deploy/args/invariant) may still be hand-built
          (M1) — this is the current real capability, honestly counted.

  TIER-2  fully autonomous, including PoC synthesis (M4.5)
          TIER-1 plus the scenario harness was machine-synthesized. Expected
          near-zero today. Named, not hidden.

  TIER-3  surfaced but not caught
          M0 tagged the finding's host function (and M2/M3 reasoned about it),
          but no gate-confirmed path. Recall-in-principle, not in-practice.

  MISSED  the host function was not even surfaced.

A separate, non-tier signal is logged: PATH_FOUND — a backend found a candidate
bypass path for the finding's mechanism, but it was NOT gate-confirmed. A path
without a verdict is NOT a catch; it is a discovery lead. Counting it as a catch
would reintroduce the hallucination M1 exists to eliminate.

State label: IMPLEMENTED (frozen).
"""

from __future__ import annotations

from enum import Enum


class Tier(str, Enum):
    TIER1 = "tier1_autonomous_path_and_verdict"
    TIER2 = "tier2_fully_autonomous_with_poc_synthesis"
    TIER3 = "tier3_surfaced_not_caught"
    MISSED = "missed"


def classify(
    *,
    surfaced: bool,
    gate_confirmed: bool,
    poc_synthesized: bool,
) -> Tier:
    """Mechanical tier assignment. No judgment, no exceptions.

    `path_found` is intentionally NOT a parameter: a found path that the gate did
    not confirm does not change the tier. It is logged elsewhere as a lead.
    """
    if gate_confirmed and poc_synthesized:
        return Tier.TIER2
    if gate_confirmed:
        return Tier.TIER1
    if surfaced:
        return Tier.TIER3
    return Tier.MISSED


# Pinned at authoring time; the scorer asserts the rules below still hold, so a
# later edit that weakens a definition trips the assertion instead of silently
# inflating the number.
FROZEN_RULES = {
    "tier1_requires_gate_confirmed": True,
    "tier2_requires_poc_synthesis": True,
    "path_found_is_not_a_catch": True,
    "tiers_never_collapsed": True,
}
