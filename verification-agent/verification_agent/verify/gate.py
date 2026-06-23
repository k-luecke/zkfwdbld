"""Verdict vocabulary for the truth gate.

The verdict is produced on-chain by VerifyGate.sol and merely interpreted here.
Keeping the taxonomy in one place lets triage/report (M5) and the meta-validation
(M1's self-proof) agree on what each outcome means.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from enum import Enum


class Verdict(str, Enum):
    # The only verdict that lets a finding leave the system.
    CONFIRMED = "CONFIRMED"

    # Rejections — each a distinct reason the gate refused to confirm.
    REJECTED_MALFORMED_BASELINE = "REJECTED_MALFORMED_BASELINE"
    REJECTED_MALFORMED_CONTROL = "REJECTED_MALFORMED_CONTROL"
    REJECTED_MALFORMED_CONTROL_REVERT = "REJECTED_MALFORMED_CONTROL_REVERT"
    REJECTED_ATTACK_REVERTED = "REJECTED_ATTACK_REVERTED"
    REJECTED_INVARIANT_INTACT = "REJECTED_INVARIANT_INTACT"

    # The harness could not obtain a verdict (compile/run failure, no marker).
    NO_VERDICT = "NO_VERDICT"

    @property
    def is_confirmed(self) -> bool:
        return self is Verdict.CONFIRMED

    @property
    def is_rejection(self) -> bool:
        return self.value.startswith("REJECTED_")

    @property
    def explanation(self) -> str:
        return {
            Verdict.CONFIRMED:
                "Invariant held at baseline, survived honest use, and was "
                "specifically broken by the attack. Execution-proven.",
            Verdict.REJECTED_MALFORMED_BASELINE:
                "Invariant was false on honest seeded state; the predicate is "
                "meaningless, so no 'break' it reports can be trusted.",
            Verdict.REJECTED_MALFORMED_CONTROL:
                "A legitimate, authorized action broke the invariant; the "
                "predicate is too brittle and would confirm honest behaviour.",
            Verdict.REJECTED_MALFORMED_CONTROL_REVERT:
                "The honest control action reverted; the scenario is not a valid "
                "baseline for judging the attack.",
            Verdict.REJECTED_ATTACK_REVERTED:
                "The exploit reverted; it never executed. Hypothesis is false.",
            Verdict.REJECTED_INVARIANT_INTACT:
                "The exploit changed on-chain state but did NOT violate the "
                "stated invariant. Passing 'for the wrong reason' — rejected.",
            Verdict.NO_VERDICT:
                "No verdict marker was produced (compile/run failure).",
        }[self]


def parse_verdict(text: str) -> Verdict:
    """Extract the VAGATE_VERDICT marker from forge's -vv output."""
    return parse_markers(text)[0]


def parse_markers(text: str) -> tuple[Verdict, str, str]:
    """Return (verdict, invariant_predicate_text, case_marker) from forge output.

    The gate emits three markers per run (VAGATE_VERDICT / VAGATE_INVARIANT /
    VAGATE_CASE). Carrying the predicate text alongside the verdict is what makes
    the run log auditable: "here is every verdict and the measuring stick it
    judged" is the artifact that proves the gate at backtest scale.
    """
    verdict = Verdict.NO_VERDICT
    invariant = ""
    case_marker = ""
    for line in text.splitlines():
        if "VAGATE_VERDICT" in line:
            tail = line.split("VAGATE_VERDICT", 1)[1].strip().split()
            if tail:
                try:
                    verdict = Verdict(tail[0])
                except ValueError:
                    pass
        elif "VAGATE_INVARIANT" in line:
            invariant = line.split("VAGATE_INVARIANT", 1)[1].strip()
        elif "VAGATE_CASE" in line:
            case_marker = line.split("VAGATE_CASE", 1)[1].strip()
    return verdict, invariant, case_marker
