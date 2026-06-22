"""A verification case: a hypothesis bound to a runnable PoC and an expectation.

For M1 these are hand-written (the milestone is "prove the gate", not "generate
the PoC"). From M3 on, the hypothesis engine produces the hypothesis and the
verify harness generates the PoC; the gate and this schema stay the same.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from dataclasses import dataclass

from .gate import Verdict


class CaseKind(str):
    KNOWN_TRUE = "known_true"        # a real, judged finding -> must CONFIRM
    FALSE = "false_hypothesis"       # plausible but wrong -> must reject (no repro)
    WRONG_REASON = "wrong_reason"    # changes state but not the invariant -> must reject
    # The gate auditing its own measuring stick: bad PREDICATES, not bad exploits.
    BAD_BASELINE = "malformed_baseline"   # predicate false at rest -> must reject
    BAD_CONTROL = "malformed_control"     # predicate broken by honest use -> must reject


@dataclass(frozen=True)
class VerificationCase:
    """One PoC the gate must rule on, with the verdict we expect."""

    case_id: str
    contract_name: str          # the Solidity case contract (forge --match-contract)
    kind: str                   # CaseKind.*
    hypothesis: str             # the claim being tested
    expected_verdict: Verdict   # what a correct gate must return
    source_finding: str = ""    # provenance, e.g. "C4 2024-01-decent M-03"
    severity: str = ""          # C4/Sherlock rubric, for confirmed findings
