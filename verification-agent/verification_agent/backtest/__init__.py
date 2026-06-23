"""Backtest harness (M6) — the number that says hunter vs verifier.

Frozen three-tier taxonomy (tiers.py), blind run (runner.py — never reads
findings), separate scoring (scorer.py — the only place answer keys open), and a
lane-honest contest set (contests.py). The scorecard obeys the same rule as the
gate: definitions fixed before the run; no post-hoc judgment.
"""

from .contests import ANSWER_KEYS, CONTESTS, in_lane
from .runner import BlindRunner
from .scorer import aggregate, score_contest
from .tiers import Tier, classify

__all__ = [
    "CONTESTS", "ANSWER_KEYS", "in_lane",
    "BlindRunner", "score_contest", "aggregate",
    "Tier", "classify",
]
