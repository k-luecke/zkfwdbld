"""Offline tests for M4.5 scenario synthesis (no forge needed).

The forge-executed proof — synthesized faithful -> CONFIRMED, synthesized rigged
-> REJECTED_MALFORMED_CONTROL — is the recorded run in examples/m45_synthesis.txt
and docs/M4.5_scenario_synthesis.md. These tests cover the Python side: that the
synthesizer generates the right scenarios, routes mechanisms honestly, and never
overclaims executability — so the *boundary* (the thing that keeps M4.5 honest)
is guarded without a toolchain.
"""

from verification_agent.synthesize import ScenarioSynthesizer


def _syn():
    return ScenarioSynthesizer()


def test_structural_lead_is_executable_with_two_cases():
    sc = _syn().synthesize({"attack_entrypoint": "receiveFromBridge",
                            "guard_bypassed": "retrieveAndCollectFees"})
    assert sc.executable
    assert sc.is_self_contained
    roles = {c.role for c in sc.cases}
    assert roles == {"faithful", "rigged-control"}


def test_faithful_expects_confirmed_rigged_expects_control_rejection():
    sc = _syn().synthesize({"attack_entrypoint": "receiveFromBridge",
                            "guard_bypassed": "retrieveAndCollectFees"})
    by_role = {c.role: c for c in sc.cases}
    # The load-bearing pair: a faithful scenario should CONFIRM; a machine-rigged
    # predicate must be caught by Control, never CONFIRMED.
    assert by_role["faithful"].expected_verdict == "CONFIRMED"
    assert by_role["rigged-control"].expected_verdict == "REJECTED_MALFORMED_CONTROL"


def test_generated_solidity_carries_independent_invariant_and_control():
    sc = _syn().synthesize({"attack_entrypoint": "receiveFromBridge",
                            "guard_bypassed": "retrieveAndCollectFees"})
    sol = sc.solidity
    # The invariant counts authorized effects (independent of the attack).
    assert "effectCount() == target.authorizedEffects()" in sol
    # The unguarded entrypoint named by the lead is the attack.
    assert "function receiveFromBridge() external" in sol
    # A guarded sibling exists (the thing the unguarded path bypasses).
    assert "guardedSibling" in sol
    # The rigged variant is the brittle predicate Control must reject.
    assert "sink.effectCount() == 0" in sol
    # Imports the real gate by relative path (the runner drops the real file there).
    assert 'import {VerifyGate} from "./VerifyGate.sol"' in sol


def test_template_is_target_agnostic_no_protocol_names():
    # If a protocol name leaked into the template, a "CONFIRM" could be rigged by
    # smuggling the answer in. The generated source must contain only the lead's
    # own names + generic scaffolding.
    sc = _syn().synthesize({"attack_entrypoint": "someEntry",
                            "guard_bypassed": "onlyOwner"})
    sol = sc.solidity.lower()
    for forbidden in ("utb", "decent", "centrifuge", "liquiditypool"):
        assert forbidden not in sol


def test_signature_permit_lead_is_not_executable_and_names_the_gap():
    sc = _syn().synthesize({"attack_entrypoint": "requestRedeemWithPermit",
                            "guard_bypassed": "withApproval"})
    assert not sc.executable
    assert sc.mechanism == "signature-scope"
    assert sc.cases == []
    # The gap is a precise work order, not a shrug.
    assert "permit" in sc.gap.lower()
    assert "eip-712" in sc.gap.lower() or "scope" in sc.gap.lower()


def test_lead_without_guard_is_not_executable():
    sc = _syn().synthesize({"attack_entrypoint": "lonelyFn", "guard_bypassed": ""})
    assert not sc.executable
    assert "guard" in sc.gap.lower()


def test_fee_gate_counts_as_structural_not_signature():
    # Decent M-03's guard is a fee/signature COLLECTION modifier the unguarded
    # path skips entirely — a structural bypass, not a signature-scope bug. It
    # must be executable (the canonical reproduce target), not rejected.
    sc = _syn().synthesize({"attack_entrypoint": "receiveFromBridge",
                            "guard_bypassed": "retrieveAndCollectFees"})
    assert sc.executable
    assert sc.mechanism == "access-control/alt-entrypoint"
