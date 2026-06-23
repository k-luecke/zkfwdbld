"""Shape-fit screener (Move A) — rank a codebase by BUG-CLASS SHAPE, not category.

The Kelp lesson, codified. Kelp was screened as an "access-control protocol" and
produced no catch: it has no alt-entrypoint shape (a permissionless path reaching an
effect a sibling GATES). "Access-control protocol" was too loose — an LST's real
bugs are accounting/oracle.

This screener answers the only question that predicts whether the loop can catch
here, from CODE STRUCTURE ALONE: does the codebase contain attacker-reachable
guarded/unguarded sibling pairs over a shared privileged effect? It runs the M0
structural surface + the Move-2 claimed-rule (sibling-asymmetry) signal + Seer's
structural reachability as a PRE-SCREEN — the same machinery the hunt uses, but to
SELECT a target instead of chasing one.

The decisive signal is Seer-pathability, not violation count: on the two contests
with ground truth, Kelp produced 7 claimed-rule candidates but Seer pathed 0 (the
candidates are initializer/unpause asymmetries, not attacker-reachable bypasses),
while Decent produced 6 candidates of which Seer paths the real M-03. So shape-fit
keys on pathable pairs; raw candidate count is only secondary evidence.

DISCIPLINE: screens on SHAPE only. It NEVER reads or ranks on judged findings — that
would break blindness. Shape-fit is a function of the structural model alone, so it
runs identically on a SETTLED contest or a LIVE competition's scope (the dual-use
contest-selection tool).

State label: IMPLEMENTED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..hypothesize import HypothesisEngine
from ..pathfind import PathOrchestrator


@dataclass
class ShapeFitReport:
    target: str
    surface_unguarded: int           # M0 structural surface size
    candidate_violations: int        # Move-2 claimed-rule candidates (hunter leads)
    pathable_pairs: int              # Seer-pathable candidates — the decisive signal
    pathable_evidence: list[dict] = field(default_factory=list)
    shape_fit: float = 0.0           # 0..1
    band: str = "NONE"               # HIGH | LOW | NONE
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "surface_unguarded": self.surface_unguarded,
            "candidate_violations": self.candidate_violations,
            "pathable_pairs": self.pathable_pairs,
            "pathable_evidence": self.pathable_evidence,
            "shape_fit": self.shape_fit,
            "band": self.band,
            "note": self.note,
        }


class ShapeScreener:
    """Scores a codebase for the alt-entrypoint shape from structure alone."""

    def __init__(self, engine: HypothesisEngine | None = None):
        self.engine = engine or HypothesisEngine()

    def screen(
        self, model: dict[str, Any], source_root: str | None = None,
        target: str | None = None,
    ) -> ShapeFitReport:
        surface = len(model.get("verification_surface", []))
        # Move-2 claimed-rule candidates (sibling asymmetry over a real effect).
        hyps = self.engine.run(model, protocol_aware=True, source_root=source_root)
        # Seer's structural reachability — does an attacker-reachable bypass exist?
        report = PathOrchestrator().run(hyps, model, run_external=False)
        paths = report.get("found_paths", [])
        evidence = [
            {"attack_entrypoint": p["attack_entrypoint"],
             "guard_bypassed": p["guard_bypassed"],
             "reaches": p["reaches"]}
            for p in paths
        ]

        n_paths = len(paths)
        n_cand = len(hyps)
        if n_paths >= 1:
            band = "HIGH"
            shape_fit = round(min(1.0, 0.6 + 0.1 * n_paths), 3)
            note = (f"{n_paths} attacker-reachable guarded/unguarded sibling pair(s) "
                    f"over a shared effect — the loop can catch here.")
        elif n_cand >= 1:
            band = "LOW"
            shape_fit = 0.2
            note = (f"{n_cand} claimed-rule candidate(s) but Seer paths NONE — "
                    f"the asymmetries are not attacker-reachable bypasses (the Kelp "
                    f"pattern). The loop will go quiet here.")
        else:
            band = "NONE"
            shape_fit = 0.0
            note = "No sibling-asymmetry candidates at all — wrong class entirely."

        return ShapeFitReport(
            target=target or model.get("repo_url") or "model",
            surface_unguarded=surface,
            candidate_violations=n_cand,
            pathable_pairs=n_paths,
            pathable_evidence=evidence,
            shape_fit=shape_fit,
            band=band,
            note=note,
        )
