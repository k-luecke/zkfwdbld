"""Hypothesis engine (M3) — connects M0's surface and M2's priors.

Move 2 makes the HUNTER sharper. The default generation mode is now
PROTOCOL-AWARE: a hypothesis targets a violation of the protocol's own STATED
RULE (a guarded sibling enforces modifier M over effect E; here is a path that
reaches E without M), not a generic structural shape ("this function is
unguarded"). Structure-alone could not tell a real violation from a legitimately
permissionless function — which is why it was loud on unfamiliar code.

The structural mode is kept (`protocol_aware=False`) so the before/after sharpening
can be measured. Either way the engine never verifies — it does not import the gate;
protocol-awareness only sharpens what gets PROPOSED.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from typing import Any

from ..kb import KnowledgeBase
from ..kb.query import query_from_surface_function
from . import ev as _ev
from .invariants import invariant_for
from .protocol_rules import RuleViolation, extract_rules_and_violations
from .provider import HypothesisProvider, OfflineHypothesisProvider, _evidence_terms
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

    def run(
        self,
        model: dict[str, Any],
        protocol_aware: bool = True,
        source_root: str | None = None,
    ) -> list[Hypothesis]:
        """Return EV-ranked candidate hypotheses for a target model (M0 JSON).

        protocol_aware (default): propose only claimed-rule violations — sharper.
        Set False to reproduce the structure-alone behaviour (for before/after).
        """
        if protocol_aware:
            hyps = self._run_protocol_aware(model, source_root)
        else:
            hyps = self._run_structural(model)
        hyps.sort(key=lambda h: h.ev.score, reverse=True)
        return hyps

    # -- structure-alone (the old, loud path; kept for measurement) --------
    def _run_structural(self, model: dict[str, Any]) -> list[Hypothesis]:
        hyps: list[Hypothesis] = []
        for fn in model.get("verification_surface", []):
            query = query_from_surface_function(fn)
            priors = self.kb.retrieve_priors(query, k=self.k_priors)
            hyps.extend(self.provider.propose(fn, priors))
        return hyps

    # -- protocol-aware (the sharper hunter) -------------------------------
    def _run_protocol_aware(
        self, model: dict[str, Any], source_root: str | None
    ) -> list[Hypothesis]:
        _, violations = extract_rules_and_violations(model, source_root)
        # One hypothesis per violating function (keep the first/strongest effect).
        by_fn: dict[str, RuleViolation] = {}
        for v in violations:
            by_fn.setdefault(v.key, v)
        surface = {f"{f.get('contract')}.{f.get('name')}": f
                   for f in model.get("verification_surface", [])}
        out: list[Hypothesis] = []
        for key, v in by_fn.items():
            fn_entry = surface.get(key) or {
                "contract": v.contract, "name": v.function,
                "surfaces": [], "surface_evidence": {}, "signature": ""}
            priors = self.kb.retrieve_priors(
                query_from_surface_function(fn_entry), k=self.k_priors)
            out.append(self._hypothesis_from_violation(v, fn_entry, priors))
        return out

    def _hypothesis_from_violation(
        self, v: RuleViolation, fn_entry: dict[str, Any], priors: list
    ) -> Hypothesis:
        # A claimed-rule violation maps to the access-control conservation
        # invariant: every privileged effect must have gone through the canonical
        # gate (the modifier M the protocol enforces on the guarded sibling).
        inv = invariant_for(
            root_cause="access-control",
            bug_class="claimed-rule-violation",
            invariant_violated=f"only-via-{v.required_modifier}-causes-{v.effect}",
            target_contract=v.contract,
            target_function=v.function,
        )
        surfaces = list(fn_entry.get("surfaces", []))
        evidence = _evidence_terms(fn_entry)
        # The stated rule is itself strong evidence; blend with any KB prior.
        prior_strength = max((priors[0].score if priors else 0.0), 0.6)
        sketch = [
            f"Reach {v.key} as an unprivileged caller (no {v.required_modifier}).",
            f"Drive the protected effect {v.effect} that the guarded sibling "
            f"{v.guarded_siblings[0] if v.guarded_siblings else '?'} gates.",
            f"Observe the break: {inv.break_expectation}",
        ]
        ev_score = _ev.score_ev(
            root_cause="access-control",
            prior_strength=prior_strength,
            surfaces=surfaces,
            evidence_terms=evidence,
            attack_steps=len(sketch),
        )
        prior_ids = [p.entry.id for p in priors[:3]]
        return Hypothesis(
            id=f"hyp::{v.key}::claimed-rule::{v.required_modifier}",
            target_contract=v.contract,
            target_function=v.function,
            surfaces=surfaces,
            bug_class="claimed-rule-violation",
            root_cause="access-control",
            invariant_violated=inv.name,
            invariant=inv,
            attack_sketch=sketch,
            ev=ev_score,
            prior_ids=prior_ids,
            prior_sources=["protocol-rule:modifier-asymmetry"]
                          + ([p.entry.source.value for p in priors[:2]]),
            statement=v.statement(),
            llm_confidence=0.0,
            generator="protocol-aware",
            claimed_rule=v.to_dict(),
        )
