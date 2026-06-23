"""Blind backtest runner — produces frozen output WITHOUT reading answer keys.

This module runs the full loop (M0 model -> M3 hypotheses -> M4 path-finding ->
M1 gate where a scenario exists) on a contest's code alone. It never imports or
reads the contest's published findings — that separation is what makes the run
blind. The scorer (scorer.py) opens the answer keys afterward.

State label: IMPLEMENTED.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..hypothesize import HypothesisEngine
from ..pathfind import PathOrchestrator


class BlindRunner:
    def __init__(self, k_priors: int = 5):
        self.k_priors = k_priors

    def run(
        self,
        contest_id: str,
        model_paths: list[str],
        repo_dir: str | None = None,
        confirm_gate: bool = True,
    ) -> dict[str, Any]:
        surfaced: set[str] = set()
        hyps = []
        engine = HypothesisEngine(k_priors=self.k_priors)
        orch = PathOrchestrator()
        found = []
        seen = set()
        for mp in model_paths:
            model = json.loads(Path(mp).read_text())
            surfaced |= {f"{f['contract']}.{f['name']}"
                         for f in model.get("verification_surface", [])}
            mh = engine.run(model)
            hyps.extend(mh)
            report = orch.run(mh, model, repo_dir=repo_dir, run_external=False)
            for r in report["found_paths"]:
                key = (r["attack_entrypoint"], r["guard_bypassed"])
                if key in seen:
                    continue
                seen.add(key)
                found.append({
                    "backend": r["backend"],
                    "attack_entrypoint": r["attack_entrypoint"],
                    "guard_bypassed": r["guard_bypassed"],
                    "reaches": r["reaches"],
                    "gate_binding": r["gate_binding"],
                })
        surfaced = sorted(surfaced)

        confirmed = []
        if confirm_gate and repo_dir:
            confirmed = self._confirm(found, repo_dir)

        return {
            "contest_id": contest_id,
            "models": model_paths,
            "counts": {
                "surfaced": len(surfaced),
                "hypotheses": len(hyps),
                "paths_found": len(found),
                "gate_confirmed": len([c for c in confirmed if c["verdict"] == "CONFIRMED"]),
            },
            "surfaced_functions": surfaced,
            "hypotheses": [
                {"target": f"{h.target_contract}.{h.target_function}",
                 "mechanism": h.root_cause, "ev": h.ev.score} for h in hyps],
            "found_paths": found,
            "gate_confirmed": confirmed,
        }

    def _confirm(self, found, repo_dir) -> list[dict]:
        # The gate lives in verify/; the runner is orchestration, so it may use
        # it. (Discovery modules kb/hypothesize/pathfind never import it.)
        from ..verify import DECENT_M1_CASES, VerifyHarness
        cases_by_binding = {c.contract_name: c for c in DECENT_M1_CASES}
        out = []
        harness = None
        for f in found:
            binding = f.get("gate_binding")
            case = cases_by_binding.get(binding) if binding else None
            if not case:
                continue
            if harness is None:
                harness = VerifyHarness(Path(repo_dir))
            r = harness.run_suite([case])[0]
            out.append({
                "binding": binding,
                "attack_entrypoint": f["attack_entrypoint"],
                "verdict": r.verdict.value,
                # The gate's deploy/invariant scenario is hand-built (M1); the
                # PATH was machine-found. PoC synthesis (M4.5) not done.
                "poc_synthesized": False,
            })
        return out
