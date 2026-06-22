"""Hypothesis engine (M3) — connects M0's surface and M2's priors.

For each function on M0's verification surface, retrieve KB priors (M2), ask the
provider to propose hypotheses grounded on them, score EV, and rank. The output
is a ranked batch of CANDIDATES that flow into the M1 gate — the engine itself
never verifies (it does not import the gate).

State label: IMPLEMENTED.
"""

from __future__ import annotations

from typing import Any

from ..kb import KnowledgeBase
from ..kb.query import query_from_surface_function
from .provider import HypothesisProvider, OfflineHypothesisProvider
from .schema import Hypothesis


class HypothesisEngine:
    def __init__(
        self,
        kb: KnowledgeBase | None = None,
        provider: HypothesisProvider | None = None,
        k_priors: int = 5,
    ):
        self.kb = kb or KnowledgeBase.from_data()
        self.provider = provider or OfflineHypothesisProvider()
        self.k_priors = k_priors

    def run(self, model: dict[str, Any]) -> list[Hypothesis]:
        """Return EV-ranked candidate hypotheses for a target model (M0 JSON)."""
        hyps: list[Hypothesis] = []
        for fn in model.get("verification_surface", []):
            query = query_from_surface_function(fn)
            priors = self.kb.retrieve_priors(query, k=self.k_priors)
            hyps.extend(self.provider.propose(fn, priors))
        # Highest EV first — this is the ordering that must deprioritize the
        # benign functions M0 over-tags.
        hyps.sort(key=lambda h: h.ev.score, reverse=True)
        return hyps
