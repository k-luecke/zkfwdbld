"""Path-backend interface.

The orchestrator dispatches a hypothesis to whichever backends are available
and apt for its mechanism shape; it does not reimplement them. Every backend
searches TOWARD the hypothesis's break predicate — a path that reaches the
contract but doesn't move the invariant is not a find.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from typing import Any, Protocol

from .schema import PathResult


class PathBackend(Protocol):
    name: str

    def available(self) -> bool:
        """Is the backend usable here (tool installed, deps present)?"""
        ...

    def find_path(
        self,
        hypothesis: Any,
        model: dict[str, Any],
        repo_dir: Any | None = None,
        timeout: int = 120,
    ) -> PathResult:
        """Search for a concrete path that drives state to the break predicate."""
        ...
