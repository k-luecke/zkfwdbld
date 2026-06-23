"""Offline tests for M4.5 deploy-graph synthesis (no forge needed).

The forge-executed proof — the machine-generated backbone spliced into a hand-built
semantic mile CONFIRMS M-03 against real Decent code — is the recorded run in
examples/m45_deploygraph_decent.txt. These tests pin the Python derivation: that the
synthesizer reads collaborators + owner-gated wiring from the model, excludes
interfaces, stays target-agnostic, and NAMES the semantic mile it cannot derive.
"""

import json
from pathlib import Path

from verification_agent.synthesize.deploygraph import DeployGraphSynthesizer

ROOT = Path(__file__).resolve().parents[1]
DECENT = ROOT / "examples" / "2024-01-decent.model.json"


def _graph():
    model = json.loads(DECENT.read_text())
    return DeployGraphSynthesizer().synthesize(model, "UTB")


def test_discovers_owner_gated_wiring_setters():
    g = _graph()
    setters = {w.setter for w in g.wiring}
    # UTB's owner-gated wiring setters, read from the model's entry points.
    assert {"setExecutor", "setFeeCollector", "registerSwapper"} <= setters


def test_matches_concrete_collaborators_not_interfaces():
    g = _graph()
    by_var = {d.var: d for d in g.deploys}
    # The fix: prefer the concrete UTBExecutor over the interface IUTBExecutor.
    assert by_var["executor"].contract == "UTBExecutor"
    assert by_var["feeCollector"].contract == "UTBFeeCollector"
    assert not by_var["executor"].is_mock_slot


def test_unmatched_slot_becomes_a_named_mock_not_a_guess():
    g = _graph()
    by_var = {d.var: d for d in g.deploys}
    # setWrapped has no in-scope concrete -> a flagged mock slot, never invented.
    assert by_var["wrapped"].is_mock_slot
    assert by_var["wrapped"].iface == "IWrapped"


def test_render_state_assignment_does_not_shadow_state_vars():
    # The bug the gate caught: local decls shadow scenario state. Assignment form
    # must NOT redeclare the type (so it assigns the pre-declared state var).
    g = _graph()
    body = g.render_seed(as_assignment=True)
    assert "target_ = new UTB();" in body
    assert "UTB target_ = new UTB();" not in body
    # The standalone (non-scenario) form does declare locals.
    assert "UTB target_ = new UTB();" in g.render_seed(as_assignment=False)


def test_names_the_semantic_mile_including_the_signature_blocker():
    g = _graph()
    gaps = " ".join(g.semantic_gaps).lower()
    # The honest frontier: the model cannot supply these. The signature is the core.
    assert "signature" in gaps
    assert "mock behaviour" in gaps or "behaviour" in gaps
    assert "payload" in gaps


def test_synthesizer_is_target_agnostic_no_protocol_literals():
    # No protocol name may be hardcoded in the synthesizer source, or a derivation
    # could be smuggled rather than derived.
    src = (ROOT / "verification_agent" / "synthesize" / "deploygraph.py").read_text().lower()
    for forbidden in ("utb", "decent", "centrifuge", "feecollector", "executescheduled"):
        assert forbidden not in src
