"""EV ranking — must earn its keep against an over-inclusive surface.

M0 deliberately over-tags (recall bias), so the surface contains benign
functions. EV's job is to deprioritize them cheaply so M3 spends LLM/verify
budget on the highest-value targets first. The recall bias upstream writes this
requirement here.

EV = severity x evidence / verify_cost, where:
- severity comes from the matched mechanism's bug *class* (access-control,
  signature, proof-forgery rank high; rounding/generic rank low);
- evidence blends how strongly a known dangerous mechanism matched (the KB
  prior score) with structural risk (unguarded + fund-moving behaviour);
- verify_cost grows with attack complexity.

A benign function matches only weak priors and has low structural risk, so its
evidence term collapses and EV stays near the floor regardless of class.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from .schema import EV

# Severity by mechanism class (maps to the C4/Sherlock impact rubric).
_SEVERITY = {
    "access-control": 1.0,
    "signature-verification": 1.0,
    "proof-forgery": 1.0,
    "cross-domain-auth": 0.9,
    "fund-routing": 0.8,
    "replay": 0.7,
    "state-machine": 0.7,
    "rounding": 0.3,
    "": 0.15,
}

_W_PRIOR = 0.7      # weight on KB-prior match strength
_W_STRUCT = 0.3     # weight on structural risk


def severity_for(root_cause: str) -> float:
    return _SEVERITY.get(root_cause, 0.2)


def structural_risk(surfaces: list[str], evidence_terms: list[str]) -> float:
    """Higher when the function is an unguarded, fund-moving entrypoint."""
    risk = 0.0
    if "unguarded_privileged_entrypoint" in surfaces:
        risk += 0.4
    terms = " ".join(evidence_terms).lower()
    if "external-call" in terms:
        risk += 0.45          # can move funds / call arbitrary targets
    if "writes-state" in terms:
        risk += 0.15
    # Keyword (vocabulary) surfaces beyond the structural one add confidence.
    keyword_surfaces = [s for s in surfaces if s != "unguarded_privileged_entrypoint"]
    if keyword_surfaces:
        risk += 0.15
    return min(risk, 1.0)


def _blast_factor(surfaces: list[str], evidence_terms: list[str]) -> float:
    """Down-weight severity for low-blast-radius functions.

    A function flagged purely on the structural rule that only writes its own
    state — no external/low-level calls, no verification-keyword surface — can't
    reach a privileged cross-contract effect. It is a legitimate suspect (the
    gate still gets to rule on it) but should not inherit a real access-control
    bug's full severity. This is what keeps a benign unguarded setter like
    contribute() off the top of the queue.
    """
    terms = " ".join(evidence_terms).lower()
    has_external = "external-call" in terms
    has_keyword_surface = any(s != "unguarded_privileged_entrypoint" for s in surfaces)
    return 1.0 if (has_external or has_keyword_surface) else 0.4


def score_ev(
    *,
    root_cause: str,
    prior_strength: float,
    surfaces: list[str],
    evidence_terms: list[str],
    attack_steps: int,
) -> EV:
    severity = severity_for(root_cause) * _blast_factor(surfaces, evidence_terms)
    struct = structural_risk(surfaces, evidence_terms)
    evidence = _W_PRIOR * prior_strength + _W_STRUCT * struct
    verify_cost = 1.0 + 0.5 * max(0, attack_steps - 1)
    score = severity * evidence / verify_cost
    return EV(
        severity=round(severity, 4),
        prior_strength=round(prior_strength, 4),
        structural_risk=round(struct, 4),
        verify_cost=round(verify_cost, 4),
        score=round(score, 4),
    )
