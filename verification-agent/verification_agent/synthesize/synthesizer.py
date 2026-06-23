"""M4.5 scenario synthesizer — turn a Seer lead into a gate scenario.

The synthesizer is the bridge from discovery (M4) to verdict (M1). Like the
backtest runner, it is allowed to produce verify inputs (it is orchestration, not
discovery) — but it NEVER decides a verdict; the unchanged gate does that.

Its most important behaviour is knowing its own limits. Two boundaries:

  1. Mechanism fit. The self-contained structural template faithfully reproduces
     an alt-entrypoint-auth-bypass (a privileged sink reached by an unguarded
     sibling). It does NOT fit a signature/permit-scope bug, where the guard is
     not absent but *satisfied by a signature whose scope is the real flaw*.
     Forcing such a lead through the structural template would confirm a bug that
     isn't the real finding — the exact rigged-harness failure mode. So those
     leads are classified non-executable, with the gap named.

  2. Self-contained vs real-code. A self-contained scenario proves the synthesis
     PIPELINE and the Control guarantee, against a target the synthesizer
     generated. It does NOT certify a real finding: only execution against the
     real deployed code can, because only the real code says whether the unguarded
     sibling truly exists and truly reaches the sink unauthorized. Certifying a
     real lead needs the protocol's deploy graph synthesized — the named M4.5
     frontier.

State label: IMPLEMENTED (self-contained) / real-code deploy synthesis = frontier.
"""

from __future__ import annotations

from typing import Any

from .schema import SynthCase, SynthScenario
from .templates import build_structural_sources

# Names that signal a signature/permit-scope mechanism the structural template
# would misrepresent (the guard is satisfied by a signature, not absent).
_SIGNATURE_MARKERS = ("permit", "withsig", "bysig", "signature", "ecrecover")


def _is_signature_lead(entrypoint: str, guard: str) -> bool:
    blob = f"{entrypoint} {guard}".lower()
    return any(m in blob for m in _SIGNATURE_MARKERS)


class ScenarioSynthesizer:
    """Generates a verify scenario from a Seer lead (dict or PathResult-like)."""

    def synthesize(self, lead: dict[str, Any]) -> SynthScenario:
        entrypoint = lead.get("attack_entrypoint") or lead.get("entrypoint") or ""
        guard = lead.get("guard_bypassed") or lead.get("guard") or ""

        # Boundary 1: signature/permit-scope leads do not fit the structural
        # template. Emit a non-executable scaffold with the precise gap.
        if _is_signature_lead(entrypoint, guard):
            return self._signature_gap(entrypoint, guard)

        # Boundary 1b: the alt-entrypoint mechanism needs a guarded sibling to
        # bypass. Seer emits `guard_bypassed` only when it found one reaching the
        # same sink; without it there is nothing structural to reproduce. The
        # guard may be an access modifier (onlyOwner) OR a value/fee/signature
        # GATE the unguarded path skips (Decent M-03's retrieveAndCollectFees) —
        # both are isomorphic to "a gated effect reached ungated".
        if not guard:
            return SynthScenario(
                lead_entrypoint=entrypoint, lead_guard=guard,
                mechanism="unclassified",
                solidity="", executable=False, is_self_contained=False,
                gap=("no bypassed guard on the lead; there is no guarded sibling "
                     "to model. Needs a path with a guarded/unguarded pair."),
                autonomy="classified-only (no scenario generated)",
            )

        # The structural gated-entrypoint case: a self-contained, executable
        # scenario (the gate may be auth or a value/fee/signature gate).
        src, faithful, rigged = build_structural_sources(entrypoint, guard)
        return SynthScenario(
            lead_entrypoint=entrypoint, lead_guard=guard,
            mechanism="access-control/alt-entrypoint",
            solidity=src,
            executable=True,
            is_self_contained=True,
            gap=("real-finding certification needs execution against the real "
                 "deployed contract (does the unguarded sibling exist and reach "
                 "the sink unauthorized?). Self-contained run proves the pipeline "
                 "+ the Control anti-rigging guarantee, not the real finding."),
            autonomy=("machine-derived: entrypoint, bypassed-guard, invariant, "
                      "control, attack, both faithful and rigged variants. "
                      "Hand-written: nothing (target-agnostic template)."),
            cases=[
                SynthCase(
                    contract_name=faithful, role="faithful",
                    case_id=f"{entrypoint}_alt_entrypoint_bypass__SYNTH_FAITHFUL",
                    expected_verdict="CONFIRMED",
                    note="unguarded sibling breaks the authorized-effect invariant",
                ),
                SynthCase(
                    contract_name=rigged, role="rigged-control",
                    case_id=f"{entrypoint}__SYNTH_RIGGED_predicate",
                    expected_verdict="REJECTED_MALFORMED_CONTROL",
                    note="machine-rigged predicate; Control must reject it",
                ),
            ],
        )

    def _signature_gap(self, entrypoint: str, guard: str) -> SynthScenario:
        return SynthScenario(
            lead_entrypoint=entrypoint, lead_guard=guard,
            mechanism="signature-scope",
            solidity="",
            executable=False,
            is_self_contained=False,
            gap=("signature/permit-scope mechanism. The structural template would "
                 "misrepresent it: the guard is not absent, it is satisfied by a "
                 "signature whose SCOPE is the bug (e.g. a permit not bound to the "
                 "pool, replayable cross-pool). A faithful scenario needs the real "
                 "protocol deployed + EIP-712 permit construction + a scope "
                 "invariant — autonomous deploy-graph + signature synthesis is the "
                 "named M4.5 frontier."),
            autonomy="classified-only (no executable scenario; mechanism out of "
                     "the structural template's honest scope)",
        )
