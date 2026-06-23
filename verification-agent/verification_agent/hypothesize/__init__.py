"""Hypothesis engine (M3) — proposes candidates; never confirms.

Connects M0's verification surface and M2's mechanism priors into ranked
candidate hypotheses whose PRIMARY output is a gate-survivable invariant
predicate. The candidates flow into the M1 gate, which alone decides truth.

Hard boundary: nothing in this package imports the verify gate. The LLM aims
the gate at good targets; it never vouches for what it aims at.
"""

from .engine import HypothesisEngine
from .provider import (
    ClaudeHypothesisProvider,
    HypothesisProvider,
    OfflineHypothesisProvider,
)
from .schema import EV, Hypothesis, InvariantSpec

__all__ = [
    "HypothesisEngine",
    "HypothesisProvider",
    "OfflineHypothesisProvider",
    "ClaudeHypothesisProvider",
    "Hypothesis",
    "InvariantSpec",
    "EV",
]
