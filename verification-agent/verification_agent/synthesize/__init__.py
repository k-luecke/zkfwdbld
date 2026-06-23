"""M4.5 — scenario synthesis: turn a machine-found path into a gate verdict.

M4 finds the path; M1 verifies a hand-built scenario. M4.5 closes the gap by
*synthesizing* the scenario (deploy + invariant + control + attack) from a Seer
lead, then running it through the UNCHANGED four-phase gate — no fast path. The
Control phase is the anti-rigging guarantee: a machine that synthesizes a rigged
predicate is rejected exactly as a human's would be.

Honest scope: the self-contained structural scenario proves the pipeline and that
guarantee; certifying a *real* finding still needs the target's deploy graph
synthesized (and, for signature/permit-scope leads, EIP-712 construction) — the
named frontier. See `SynthScenario.executable` / `.gap`.
"""

from .runner import SynthesisRunner, SynthResult
from .schema import SynthCase, SynthScenario
from .synthesizer import ScenarioSynthesizer

__all__ = [
    "ScenarioSynthesizer",
    "SynthScenario", "SynthCase",
    "SynthesisRunner", "SynthResult",
]
