"""The M1 self-proof: three cases the gate must rule on correctly.

Anchored on the settled Code4rena 2024-01-decent contest, against which M0 was
also run — closing the loop on the exact codebase we modeled. The known-true
case is a real judged Medium (M-03); the other two are the two flavours of
"bogus" the gate must catch.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from .case import CaseKind, VerificationCase
from .gate import Verdict

# Shared scenario lives in solidity/DecentFeeBypass.t.sol; each case is one
# contract differing only in runAttack().
DECENT_M1_CASES: list[VerificationCase] = [
    VerificationCase(
        case_id="M03_receiveFromBridge_unauth_fee_bypass",
        contract_name="DecentReceiveFromBridgeBypass",
        kind=CaseKind.KNOWN_TRUE,
        hypothesis=(
            "UTB.receiveFromBridge is public with no access control and calls "
            "_swapAndExecute directly, skipping the retrieveAndCollectFees "
            "modifier. An attacker executes a swap+payload with no signature and "
            "pays no fee, breaking the invariant 'every swap-execute is fee/sig "
            "gated'."
        ),
        expected_verdict=Verdict.CONFIRMED,
        source_finding="Code4rena 2024-01-decent M-03 (issue #590)",
        severity="Medium",
    ),
    VerificationCase(
        case_id="forged_signature_passes_collectFees__FALSE",
        contract_name="DecentForgedSignatureFalse",
        kind=CaseKind.FALSE,
        hypothesis=(
            "A forged ECDSA signature passes UTBFeeCollector.collectFees and "
            "bypasses the fee check in swapAndExecute."
        ),
        # The require(recovered == signer) holds; the call reverts; nothing runs.
        expected_verdict=Verdict.REJECTED_ATTACK_REVERTED,
        source_finding="(constructed negative control)",
    ),
    VerificationCase(
        case_id="paid_swap_claimed_as_bypass__WRONG_REASON",
        contract_name="DecentPaidSwapWrongReason",
        kind=CaseKind.WRONG_REASON,
        hypothesis=(
            "A fully-valid, fully-PAID swapAndExecute is claimed to demonstrate a "
            "fee bypass. The transaction succeeds and changes on-chain state, but "
            "the fee IS paid, so the invariant is not violated. A gate that only "
            "checks 'did the tx do something' would launder this into a finding."
        ),
        # The discriminator: state changed, no revert, invariant intact -> reject.
        expected_verdict=Verdict.REJECTED_INVARIANT_INTACT,
        source_finding="(constructed wrong-reason control)",
    ),
    VerificationCase(
        case_id="malformed_baseline__predicate_false_at_rest",
        contract_name="DecentMalformedBaseline",
        kind=CaseKind.BAD_BASELINE,
        hypothesis=(
            "The invariant predicate is false on honest seeded state "
            "(feeCollector.balance > 0 at baseline). A predicate false at rest "
            "cannot witness a break, so the gate must refuse to proceed."
        ),
        # The gate audits the measuring stick: stops before the attack.
        expected_verdict=Verdict.REJECTED_MALFORMED_BASELINE,
        source_finding="(constructed bad-predicate control)",
    ),
    VerificationCase(
        case_id="malformed_control__predicate_broken_by_honest_use",
        contract_name="DecentMalformedControl",
        kind=CaseKind.BAD_CONTROL,
        hypothesis=(
            "The predicate (target.pwnedCount == 0) holds at baseline but is too "
            "brittle: a legitimate, fully-paid swap breaks it by design. If "
            "trusted, it would yield a false CONFIRMED; Control must catch it "
            "before the attack is judged."
        ),
        # The last load-bearing guard, proven firing on camera.
        expected_verdict=Verdict.REJECTED_MALFORMED_CONTROL,
        source_finding="(constructed bad-predicate control)",
    ),
]
