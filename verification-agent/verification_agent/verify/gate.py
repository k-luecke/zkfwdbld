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
    marker = "VAGATE_VERDICT"
    for line in text.splitlines():
        if marker in line:
            tail = line.split(marker, 1)[1].strip()
            token = tail.split()[0] if tail.split() else ""
            try:
                return Verdict(token)
            except ValueError:
                continue
    return Verdict.NO_VERDICT
