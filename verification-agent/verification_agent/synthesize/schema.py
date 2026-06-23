"""M4.5 synthesis schema — a machine-generated scenario, honestly bounded.

A `SynthScenario` is the bridge artifact between a Seer lead (M4) and the verify
gate (M1): the generated Solidity, the gate cases it defines, and — the part that
keeps M4.5 honest — an explicit `autonomy` boundary that records what was
machine-derived versus what a real-code reproduction still needs.

Two honesty fields do the load-bearing work:

  executable  — can this scenario be fork-executed to a real verdict *right now*?
                A self-contained structural scenario is executable (it generates
                its own faithful target). A real-protocol lead is NOT, until the
                deploy graph + any signature construction is synthesized.

  gap         — when not executable, the precise named blocker (the work order),
                so "M4.5 isn't done" is a diagnosis, never a shrug.

State label: IMPLEMENTED (self-contained pipeline) / the real-code deploy-graph
synthesis is the named frontier — see `executable`/`gap`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SynthCase:
    """One generated gate case: a Solidity contract name + expected verdict."""

    contract_name: str
    role: str               # "faithful" | "rigged-control"
    case_id: str
    expected_verdict: str   # what a correct gate must return on the generated target
    note: str = ""


@dataclass
class SynthScenario:
    """A machine-synthesized verify scenario derived from a Seer lead."""

    lead_entrypoint: str
    lead_guard: str
    mechanism: str
    solidity: str                       # the generated .sol source (may be a scaffold)
    cases: list[SynthCase] = field(default_factory=list)
    executable: bool = False            # can it reach a real verdict now?
    is_self_contained: bool = False     # generates its own target (not real code)
    gap: str = ""                       # if not executable, the named blocker
    autonomy: str = ""                  # what was machine-derived vs left as TODO

    def to_dict(self) -> dict[str, Any]:
        return {
            "lead_entrypoint": self.lead_entrypoint,
            "lead_guard": self.lead_guard,
            "mechanism": self.mechanism,
            "executable": self.executable,
            "is_self_contained": self.is_self_contained,
            "gap": self.gap,
            "autonomy": self.autonomy,
            "cases": [
                {"contract": c.contract_name, "role": c.role,
                 "case_id": c.case_id, "expected_verdict": c.expected_verdict,
                 "note": c.note}
                for c in self.cases
            ],
        }
