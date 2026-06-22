"""Path-finding schema — the per-backend, per-mechanism coverage record.

M4 either proves the system can DISCOVER paths or reveals it can only verify.
The honest picture is a log: for each (hypothesis, backend), did the engine find
a concrete path that drives state toward the break predicate, time out, find
nothing, or was it unavailable? That log is the discovery-coverage map — the
artifact that says which bug classes are reachable today.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class PathStatus(str, Enum):
    FOUND = "found"               # a concrete path toward the break predicate
    NO_PATH = "no_path"           # searched, found nothing
    OUT_OF_SCOPE = "out_of_scope" # this backend doesn't handle this mechanism
    TIMEOUT = "timeout"           # budget exhausted
    UNAVAILABLE = "unavailable"   # backend tool not installed
    ERROR = "error"


@dataclass
class PathResult:
    backend: str
    hypothesis_id: str
    target: str                       # contract.function (the hypothesis target)
    mechanism: str                    # root_cause class searched for
    status: PathStatus
    found: bool = False
    attack_entrypoint: str | None = None   # the function an attacker calls
    call_sequence: list[str] = field(default_factory=list)
    reaches: list[str] = field(default_factory=list)        # privileged sinks reached
    guard_bypassed: str | None = None      # the modifier/check the path skips
    # Optional binding to a runnable gate case (data only; not an import).
    gate_binding: str | None = None
    elapsed_s: float = 0.0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d
