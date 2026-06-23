"""Path orchestrator — dispatch hypotheses to backends; build the coverage map.

The orchestrator picks the backend per hypothesis shape; it does not reimplement
them. Its product is the per-backend, per-mechanism coverage log: an honest map
of which discovery engine reaches which bug class today. A backend that times out
or finds nothing is information, not failure.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from typing import Any

from .backend import PathBackend
from .halmos import HalmosBackend
from .medusa import MedusaBackend
from .schema import PathResult, PathStatus
from .seer import SeerStructuralBackend


def default_backends() -> list[PathBackend]:
    return [SeerStructuralBackend(), MedusaBackend(), HalmosBackend()]


class PathOrchestrator:
    def __init__(self, backends: list[PathBackend] | None = None):
        self.backends = backends or default_backends()

    def run(
        self,
        hypotheses: list,
        model: dict[str, Any],
        repo_dir: Any | None = None,
        run_external: bool = False,
        external_timeout: int = 90,
    ) -> dict[str, Any]:
        """Search each hypothesis with apt backends; return results + coverage.

        Seer (pure structural reasoning) always runs. The external tool backends
        (medusa/halmos) are invoked only when ``run_external`` is set, since they
        compile + fuzz/solve and are environment-bounded — their availability is
        always reported regardless.
        """
        results: list[PathResult] = []
        for h in hypotheses:
            for b in self.backends:
                is_seer = isinstance(b, SeerStructuralBackend)
                if not is_seer and not run_external:
                    continue
                if not b.available():
                    results.append(PathResult(
                        backend=b.name, hypothesis_id=getattr(h, "id", "?"),
                        target=f"{h.target_contract}.{h.target_function}",
                        mechanism=getattr(h, "root_cause", ""),
                        status=PathStatus.UNAVAILABLE, notes="backend tool not installed"))
                    continue
                results.append(b.find_path(h, model, repo_dir=repo_dir,
                                           timeout=external_timeout))
        return {
            "backends": [{"name": b.name, "available": b.available()} for b in self.backends],
            "results": [r.to_dict() for r in results],
            "coverage": self._coverage(results),
            "found_paths": [r.to_dict() for r in results if r.found],
        }

    @staticmethod
    def _coverage(results: list[PathResult]) -> dict[str, Any]:
        by_backend: dict[str, dict[str, int]] = {}
        by_mechanism: dict[str, dict[str, list[str]]] = {}
        for r in results:
            bb = by_backend.setdefault(r.backend, {})
            bb[r.status.value] = bb.get(r.status.value, 0) + 1
            bm = by_mechanism.setdefault(r.mechanism or "(none)", {})
            if r.found:
                bm.setdefault("found_by", [])
                if r.backend not in bm["found_by"]:
                    bm["found_by"].append(r.backend)
        return {"by_backend": by_backend, "by_mechanism": by_mechanism}
