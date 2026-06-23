"""Hypothesis schema — a question for the gate, never an answer.

Two boundaries are encoded in these types, mirroring the KB's prior-not-verdict
rule but enforced harder because an LLM enters the loop here:

1. **M3 proposes; it never confirms.** A `Hypothesis` carries no verdict field
   and cannot express one. `is_candidate` is always True. The LLM's
   `llm_confidence` is advisory metadata with ZERO weight on any verdict — a
   hypothesis the model is 99% sure of and one it's 30% sure of are handed to
   the gate identically. Nothing in `hypothesize/` imports the verify gate
   (enforced by a test); the only path from a hypothesis to a verdict runs
   through M1, which re-derives truth by execution.

2. **The predicate is the primary output.** The most valuable thing M3 produces
   is not the attack sketch — it's a well-formed, mechanism-specific
   `InvariantSpec` that will survive the gate's Baseline and Control phases. A
   great attack idea with a sloppy predicate just yields MALFORMED_CONTROL
   rejections. Predicate quality is M3's real output metric.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class InvariantSpec:
    """The measuring stick the gate will judge — M3's primary output.

    Defined independently of the attack, with explicit baseline/control/break
    expectations so the gate's three guards have something concrete to check.
    The Solidity instantiation is generated downstream (M4); here we produce the
    mechanism-specific specification.
    """

    name: str                       # e.g. "authorization-conservation"
    predicate_kind: str             # pattern id from the invariant library
    description: str                # the predicate in words, mechanism-specific
    baseline_expectation: str       # must hold on honest seeded state
    control_expectation: str        # a legitimate action must preserve it
    break_expectation: str          # the attack must specifically violate it
    measured_quantity: str = ""     # what to read on-chain (e.g. counts)
    # Optional: the name of an existing VerifyGate case that instantiates this
    # predicate in runnable Solidity. Data only — a string, not an import.
    gate_binding: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EV:
    """Expected value of pursuing this hypothesis, against an over-inclusive
    surface. Must be good enough to cheaply DEPRIORITIZE the benign functions
    M0 deliberately over-tags (the recall bias writes this requirement)."""

    severity: float                 # 0..1, from the matched mechanism's class
    prior_strength: float           # 0..1, how strongly a known bug class matches
    structural_risk: float          # 0..1, fund-moving / unguarded behaviour
    verify_cost: float              # >=1, estimated cost to fork-verify
    score: float                    # the ranked EV

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Hypothesis:
    """A candidate for the gate — proposes, never confirms."""

    id: str
    target_contract: str
    target_function: str
    surfaces: list[str]
    # Mechanism, grounded on a KB prior (M2). Provenance carried for the LEARN
    # loop and for measuring which source is driving hypotheses.
    bug_class: str
    root_cause: str
    invariant_violated: str
    invariant: InvariantSpec
    attack_sketch: list[str]
    ev: EV
    prior_ids: list[str] = field(default_factory=list)
    prior_sources: list[str] = field(default_factory=list)
    statement: str = ""             # one-line hypothesis ("X reaches a state violating Y")
    # Advisory only. ZERO weight on any verdict. Present so the gate can be shown
    # to ignore it.
    llm_confidence: float = 0.0
    generator: str = "offline"      # offline | claude

    # Move 2: the protocol's own stated rule this hypothesis attacks (a PRIOR, not
    # truth). Present when generation was gated by a claimed-rule violation.
    claimed_rule: dict[str, Any] | None = None

    # Hard guardrail, visible at every call site.
    is_candidate: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id,
            "target": f"{self.target_contract}.{self.target_function}",
            "statement": self.statement,
            "surfaces": self.surfaces,
            "bug_class": self.bug_class,
            "root_cause": self.root_cause,
            "invariant_violated": self.invariant_violated,
            "invariant": self.invariant.to_dict(),
            "attack_sketch": self.attack_sketch,
            "ev": self.ev.to_dict(),
            "prior_ids": self.prior_ids,
            "prior_sources": self.prior_sources,
            "llm_confidence": self.llm_confidence,
            "generator": self.generator,
            "claimed_rule": self.claimed_rule,
            "is_candidate": self.is_candidate,  # always True
            "gate_binding": self.invariant.gate_binding,
        }
        return d
