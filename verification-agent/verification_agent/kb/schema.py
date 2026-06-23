"""Knowledge-base schema — mechanism-structured, dual-source, prior-only.

Two design commitments are encoded directly in these types:

1. **Retrieve on mechanism, not prose.** A KBEntry is not a blob of finding
   text; it carries structured mechanism fields (bug_class, root_cause_category,
   invariant_violated, entrypoint_shape, surfaces). Retrieval keys on those, so
   M3 gets "same class of invariant broke the same way" rather than "mentions
   the word bridge".

2. **The KB is a hypothesis PRIOR, never a verdict.** A retrieved entry is a
   reason to investigate, never a reason to report. `PriorMatch.is_verdict` is
   `False` by construction and there is deliberately no field that could carry a
   confirmation. The gate (M1) independently confirms every finding, every time.
   The retrieval makes you fast; the gate keeps you honest. They stay separate.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Source(str, Enum):
    """Distinct retrieval sources, kept separate so M3 can blend AND measure.

    OAK is the *taxonomy* — what kinds of attacks exist on a surface (the
    hypothesis-generation scaffold). Findings/incidents are *worked examples* —
    how the attack actually manifested in real code (the concrete priors).
    """

    OAK_TAXONOMY = "oak_taxonomy"
    CONTEST_FINDING = "contest_finding"
    PUBLIC_INCIDENT = "public_incident"


@dataclass
class KBEntry:
    id: str
    source: Source
    title: str
    # --- mechanism fields: the load-bearing, retrieved-on signal ---
    surfaces: list[str]            # SurfaceCategory values (M0's lane tags)
    bug_class: str                 # short slug, e.g. "alt-entrypoint-auth-bypass"
    root_cause_category: str       # e.g. "access-control", "replay", "proof-forgery"
    invariant_violated: str        # e.g. "access-control-consistency", "replay-resistance"
    entrypoint_shape: str          # e.g. "public fn reaching a privileged action w/o the auth modifier"
    mechanism: str                 # 1-3 sentences describing HOW it breaks
    # --- supporting ---
    mitigation: str = ""
    provenance: str = ""           # contest/incident name + ref
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source"] = self.source.value
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "KBEntry":
        d = dict(d)
        d["source"] = Source(d["source"])
        return KBEntry(**d)


@dataclass
class KBQuery:
    """A retrieval query. Built from an M0 verification-surface function (see
    query.py) plus any mechanism hints M3 has formed."""

    surfaces: list[str]
    text: str = ""                 # free text: fn name/signature/context
    entrypoint_shape: str = ""
    root_cause_hint: str = ""      # optional mechanism narrowing
    invariant_hint: str = ""


@dataclass
class PriorMatch:
    """A retrieved prior. NOT a verdict — see module docstring."""

    entry: KBEntry
    score: float
    component_scores: dict[str, float]

    # Hard guardrail, present so the boundary is visible at every call site.
    is_verdict: bool = False

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.entry.id,
            "source": self.entry.source.value,
            "title": self.entry.title,
            "bug_class": self.entry.bug_class,
            "root_cause": self.entry.root_cause_category,
            "invariant": self.entry.invariant_violated,
            "surfaces": self.entry.surfaces,
            "score": round(self.score, 4),
            "components": {k: round(v, 4) for k, v in self.component_scores.items()},
            "provenance": self.entry.provenance,
            "is_verdict": self.is_verdict,  # always False
        }
