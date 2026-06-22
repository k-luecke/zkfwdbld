"""The verify gate — the truth gate that makes findings trustworthy.

verify-or-discard: a finding is CONFIRMED only when an independently defined
invariant holds at baseline, survives honest use, and is specifically broken by
the attack. See VerifyGate.sol for the on-chain protocol and gate.py for the
verdict taxonomy.
"""

from .case import CaseKind, VerificationCase
from .cases import DECENT_M1_CASES
from .gate import Verdict, parse_verdict
from .harness import CaseResult, VerifyHarness

__all__ = [
    "CaseKind",
    "VerificationCase",
    "DECENT_M1_CASES",
    "Verdict",
    "parse_verdict",
    "CaseResult",
    "VerifyHarness",
]
