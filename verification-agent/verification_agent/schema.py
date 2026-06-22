"""Typed data model emitted by the M0 harness.

The harness produces a single JSON document (the "target model") that every
downstream stage of the loop consumes. Keeping it as plain dataclasses with an
explicit ``to_dict`` keeps the on-disk contract stable and reviewable.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


SCHEMA_VERSION = "0.1.0"


class SurfaceCategory(str, Enum):
    """The verification/reachability surfaces this agent specializes in.

    These are the bug classes commodity AI auditors miss; functions tagged
    with any of these are PRIORITY for every downstream stage.
    """

    SIGNATURE_PROOF = "signature_proof_verification"
    MERKLE_STATE_PROOF = "merkle_state_proof"
    BRIDGE_INBOUND = "bridge_inbound_handler"
    CROSS_DOMAIN_AUTH = "cross_domain_auth"
    SLASHING_AVS = "slashing_avs_state"


@dataclass
class FunctionInfo:
    """One externally reachable function (entry point candidate)."""

    contract: str
    name: str
    signature: str
    visibility: str = "unknown"
    mutability: str = "unknown"
    modifiers: list[str] = field(default_factory=list)
    is_entry_point: bool = False
    # Surfaces this function was tagged with, plus the evidence that triggered
    # each tag, so a human reviewer can audit the heuristic's decision.
    surfaces: list[str] = field(default_factory=list)
    surface_evidence: dict[str, list[str]] = field(default_factory=dict)
    source_file: str | None = None
    source_line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StorageSlot:
    """A single declared storage variable (accounting/auth/money state)."""

    contract: str
    name: str
    type: str
    slot: int | None = None
    offset: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CallEdge:
    """A directed edge in the call graph (internal or external)."""

    caller: str
    callee: str
    external: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ContractInfo:
    name: str
    kind: str = "contract"  # contract | interface | library | abstract
    inheritance: list[str] = field(default_factory=list)  # C3 linearization
    source_file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolStatus:
    """Honest record of which external tools actually ran.

    A model assembled without Slither is degraded; never let downstream
    stages (or the report drafter) imply more certainty than was established.
    """

    name: str
    available: bool
    ran: bool
    version: str | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TargetModel:
    """The complete M0 output for one target."""

    repo_url: str
    commit: str | None
    build_system: str  # foundry | hardhat | unknown
    compiled: bool
    schema_version: str = SCHEMA_VERSION
    # Provenance of the model: which tools ran, degraded modes, etc.
    tool_status: list[ToolStatus] = field(default_factory=list)
    contracts: list[ContractInfo] = field(default_factory=list)
    storage_layout: list[StorageSlot] = field(default_factory=list)
    entry_points: list[FunctionInfo] = field(default_factory=list)
    call_graph: list[CallEdge] = field(default_factory=list)
    # The headline: functions on the verification/reachability priority surface.
    verification_surface: list[FunctionInfo] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repo_url": self.repo_url,
            "commit": self.commit,
            "build_system": self.build_system,
            "compiled": self.compiled,
            "tool_status": [t.to_dict() for t in self.tool_status],
            "contracts": [c.to_dict() for c in self.contracts],
            "storage_layout": [s.to_dict() for s in self.storage_layout],
            "entry_points": [f.to_dict() for f in self.entry_points],
            "call_graph": [e.to_dict() for e in self.call_graph],
            "verification_surface": [f.to_dict() for f in self.verification_surface],
            "notes": self.notes,
        }
