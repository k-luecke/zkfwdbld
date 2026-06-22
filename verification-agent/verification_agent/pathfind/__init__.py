"""Path backends (M4) — find a concrete path toward the break predicate.

Seer (structural reachability) is the reasoning core and runs everywhere;
Medusa (stateful fuzz) and Halmos (symbolic) are wired behind the same
interface. Every backend searches TOWARD the hypothesis's break predicate; the
gate confirms whether the path actually reached it. The orchestrator's product
is an honest per-backend, per-mechanism coverage map.

Reproduce-before-discover: Seer independently rediscovers the known M-03 path
(receiveFromBridge bypassing retrieveAndCollectFees) from the M0 model alone.
"""

from .backend import PathBackend
from .halmos import HalmosBackend
from .medusa import MedusaBackend
from .orchestrator import PathOrchestrator, default_backends
from .schema import PathResult, PathStatus
from .seer import SeerStructuralBackend

__all__ = [
    "PathBackend",
    "PathResult",
    "PathStatus",
    "SeerStructuralBackend",
    "MedusaBackend",
    "HalmosBackend",
    "PathOrchestrator",
    "default_backends",
]
