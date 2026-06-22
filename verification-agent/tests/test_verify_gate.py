"""Offline tests for the verify-gate plumbing (no forge/network needed).

The on-chain gate logic is validated by running the three cases through forge
(see docs/M1_verify_gate.md for the recorded run). These tests cover the Python
side: verdict parsing, the taxonomy, and the M1 case registry's internal
consistency — so a typo in the expected verdicts is caught without a toolchain.
"""

from verification_agent.verify import (
    DECENT_M1_CASES,
    Verdict,
    parse_verdict,
)
from verification_agent.verify.case import CaseKind


def test_parse_verdict_from_forge_output():
    sample = (
        "Ran 1 test for test/_vagent/DecentFeeBypass.t.sol\n"
        "[PASS] testGate() (gas: 6566358)\n"
        "Logs:\n"
        "  VAGATE_CASE M03_receiveFromBridge_unauth_fee_bypass\n"
        "  VAGATE_INVARIANT UTB swap-executes are signature/fee gated\n"
        "  VAGATE_VERDICT CONFIRMED\n"
        "Suite result: ok. 1 passed; 0 failed; 0 skipped\n"
    )
    assert parse_verdict(sample) is Verdict.CONFIRMED


def test_parse_verdict_missing_marker():
    assert parse_verdict("compiler error\nnothing here") is Verdict.NO_VERDICT


def test_parse_verdict_each_value_roundtrips():
    for v in Verdict:
        if v is Verdict.NO_VERDICT:
            continue
        assert parse_verdict(f"  VAGATE_VERDICT {v.value}") is v


def test_confirmed_and_rejection_flags():
    assert Verdict.CONFIRMED.is_confirmed
    assert not Verdict.CONFIRMED.is_rejection
    assert Verdict.REJECTED_INVARIANT_INTACT.is_rejection
    assert not Verdict.REJECTED_INVARIANT_INTACT.is_confirmed


def test_m1_case_registry_shape():
    # Exactly the three flavours the gate must distinguish, each distinct.
    kinds = {c.kind for c in DECENT_M1_CASES}
    assert kinds == {CaseKind.KNOWN_TRUE, CaseKind.FALSE, CaseKind.WRONG_REASON}

    by_kind = {c.kind: c for c in DECENT_M1_CASES}
    # The known-true case must be the only one expected to CONFIRM.
    assert by_kind[CaseKind.KNOWN_TRUE].expected_verdict is Verdict.CONFIRMED
    confirms = [c for c in DECENT_M1_CASES
                if c.expected_verdict is Verdict.CONFIRMED]
    assert len(confirms) == 1

    # The wrong-reason case is the one that must be rejected despite changing
    # state — the assertion that separates a truth gate from a compile check.
    assert (by_kind[CaseKind.WRONG_REASON].expected_verdict
            is Verdict.REJECTED_INVARIANT_INTACT)
    # The false hypothesis must be rejected because nothing reproduced.
    assert (by_kind[CaseKind.FALSE].expected_verdict
            is Verdict.REJECTED_ATTACK_REVERTED)

    # Contract names are unique (forge --match-contract targets).
    assert len({c.contract_name for c in DECENT_M1_CASES}) == len(DECENT_M1_CASES)
