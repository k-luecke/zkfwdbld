"""Offline tests for Move 2 — protocol-aware hypothesis generation.

The point of Move 2 is a SHARPER hunter, measured by confirmed-to-leads ratio,
not lead count. These tests pin the discriminator (a claimed-rule violation = a
guarded sibling enforces M over effect E; a path reaches E without M), the
target-agnostic source, the wall (no verify import), and the before/after
sharpening on the two contests with known answers.
"""

import json
from pathlib import Path

from verification_agent.hypothesize import HypothesisEngine
from verification_agent.hypothesize.protocol_rules import (
    extract_rules_and_violations,
)

ROOT = Path(__file__).resolve().parents[1]
DECENT = ROOT / "examples" / "2024-01-decent.model.json"
CENTRIFUGE = ROOT / "examples" / "2023-09-centrifuge.model.json"


def _model(p):
    return json.loads(Path(p).read_text())


def test_decent_keeps_m03_as_a_claimed_rule_violation():
    _, viol = extract_rules_and_violations(_model(DECENT))
    keys = {v.key for v in viol}
    # M-03: receiveFromBridge reaches a guarded internal effect that the guarded
    # sibling (swapAndExecute, modifier retrieveAndCollectFees) protects. With
    # the whole-program call graph, the chain is receiveFromBridge -> _swapAndExecute
    # -> performSwap; both qualified internal effects are valid violations.
    assert "UTB.receiveFromBridge" in keys
    m03s = [v for v in viol if v.key == "UTB.receiveFromBridge"
            and v.required_modifier == "retrieveAndCollectFees"]
    assert m03s, "no retrieveAndCollectFees-guarded effect found for receiveFromBridge"
    effects = {v.effect for v in m03s}
    assert effects & {"UTB._swapAndExecute", "UTB.performSwap"}, (
        f"expected an in-scope qualified internal effect, got {effects}")


def test_trivial_shared_callees_are_not_treated_as_effects():
    # The discriminator must not pair siblings over control-flow / pure helpers
    # (require/_msgSender/getters/converters) — that was the Centrifuge noise.
    # Qualified internal effects (Contract.fn) ARE valid; the noise filter rejects
    # IR-string leaks and parameterized builtins.
    _, viol = extract_rules_and_violations(_model(CENTRIFUGE))
    for v in viol:
        e = v.effect.lower()
        assert "require" not in e and "_msgsender" not in e
        assert "tobytes32" not in e and "toaddress" not in e
        assert "HIGH_LEVEL_CALL" not in v.effect and "TUPLE_" not in v.effect
        assert "(" not in v.effect


def test_protocol_aware_sharpens_decent_ratio():
    model = _model(DECENT)
    before = HypothesisEngine().run(model, protocol_aware=False)
    after = HypothesisEngine().run(model, protocol_aware=True)
    confirmed_host = "UTB.receiveFromBridge"   # the gate-CONFIRMED M-03 (keystone)

    def ratio(hyps):
        hosts = {f"{h.target_contract}.{h.target_function}" for h in hyps}
        conf = 1 if confirmed_host in hosts else 0
        return len(hyps), conf, (conf / len(hyps) if hyps else 0.0)

    bL, bC, bR = ratio(before)
    aL, aC, aR = ratio(after)
    # The headline: fewer leads, M-03 retained, ratio UP (sharper, not louder).
    assert aL < bL
    assert aC == 1 and bC == 1            # M-03 retained both ways
    assert aR > bR                        # confirmed-to-leads ratio improved


def test_protocol_aware_goes_quiet_on_centrifuge_false_positives():
    model = _model(CENTRIFUGE)
    before = HypothesisEngine().run(model, protocol_aware=False)
    after = HypothesisEngine().run(model, protocol_aware=True)
    # Centrifuge's structural leads were ALL design-permissionless false positives
    # (its real findings are non-structural). The hunter must go much quieter.
    # After the 2026-06-30 precision-regression fix (qualified-modifier filter,
    # structural library marking, low_level_call to NOISE_EXACT, library bodies
    # not emitting outgoing edges), the only remaining leads are the
    # pre-registered Root.pause "OR-authorized-path" shape (category D),
    # documented at docs/SEQUENCE_PRE_REGISTRATION.md.
    assert len(before) > 20
    assert len(after) < len(before) // 4


def test_extractor_is_target_agnostic_no_protocol_literals():
    src = (ROOT / "verification_agent" / "hypothesize" / "protocol_rules.py").read_text().lower()
    for forbidden in ("decent", "utb", "centrifuge", "receivefrombridge",
                      "retrieveandcollect", "gateway", "poolmanager"):
        assert forbidden not in src


def test_hypothesize_does_not_import_verify():
    # The wall still holds: M3 proposes, never confirms — no verify import.
    pkg = ROOT / "verification_agent" / "hypothesize"
    offenders = []
    for py in pkg.glob("*.py"):
        for line in py.read_text().splitlines():
            s = line.strip()
            if s.startswith(("import ", "from ")) and "verify" in s:
                offenders.append((py.name, s))
    assert not offenders, f"hypothesize must not import verify: {offenders}"


def test_claimed_rule_provenance_is_carried_and_is_a_prior():
    model = _model(DECENT)
    h = next(h for h in HypothesisEngine().run(model)
             if h.target_function == "receiveFromBridge")
    # The rule is recorded as provenance (a prior), and the hypothesis is still a
    # candidate, never a verdict.
    assert h.claimed_rule is not None
    assert h.claimed_rule["required_modifier"] == "retrieveAndCollectFees"
    assert h.is_candidate is True
    assert h.llm_confidence == 0.0
