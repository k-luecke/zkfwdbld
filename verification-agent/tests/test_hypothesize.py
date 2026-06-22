"""Offline tests for the M3 hypothesis engine.

Cover the load-bearing design properties: proposes-never-confirms (a structural
wall, not discipline), the predicate as primary output, and EV ranking that
deprioritizes a benign over-tagged function. No network / no LLM.
"""

import inspect
import json
from pathlib import Path

from verification_agent.hypothesize import HypothesisEngine, Hypothesis
from verification_agent.hypothesize import ev as ev_mod

ROOT = Path(__file__).resolve().parents[1]
DECENT = ROOT / "examples" / "2024-01-decent.model.json"
FIXTURE = ROOT / "examples" / "surface_sampler.model.json"


def _run(model_path):
    model = json.loads(Path(model_path).read_text())
    return HypothesisEngine().run(model)


def test_engine_produces_ranked_hypotheses():
    hyps = _run(DECENT)
    assert hyps, "expected hypotheses for the decent surface"
    # EV-sorted descending.
    scores = [h.ev.score for h in hyps]
    assert scores == sorted(scores, reverse=True)
    # The real M-03 function is present and bound to a runnable gate case.
    bound = [h for h in hyps if h.invariant.gate_binding]
    assert any(h.target_function == "receiveFromBridge" for h in bound)


def test_predicate_is_well_formed():
    # The predicate is M3's primary output — every one must have the three
    # gate-facing expectations populated, or it would MALFORMED at the gate.
    for h in _run(DECENT):
        inv = h.invariant
        assert inv.name and inv.description
        assert inv.baseline_expectation and inv.control_expectation
        assert inv.break_expectation


def test_ev_deprioritizes_benign_overtag():
    # The fixture surface includes contribute(): an unguarded state-changer with
    # no external call and no verification keyword — benign, low blast radius.
    hyps = _run(FIXTURE)
    by_name = {h.target_function: h for h in hyps}
    assert "contribute" in by_name
    # It must sink below the genuinely dangerous functions.
    assert by_name["contribute"].ev.score == min(h.ev.score for h in hyps)
    assert by_name["contribute"].ev.score < by_name["relayMessage"].ev.score
    assert by_name["contribute"].ev.score < by_name["claimWithSig"].ev.score


def test_proposes_never_confirms():
    h = _run(DECENT)[0]
    # No verdict field exists or can be expressed.
    assert h.is_candidate is True
    assert not hasattr(h, "verdict")
    d = h.to_dict()
    assert d["is_candidate"] is True
    assert "verdict" not in d
    # LLM confidence is present but carries zero weight on EV: score_ev has no
    # confidence parameter at all.
    assert "confidence" not in inspect.signature(ev_mod.score_ev).parameters


def test_hypothesize_does_not_import_the_gate():
    # The hard structural wall: nothing in hypothesize/ may import the verify
    # gate. Discovery makes the agent fast; the gate keeps it honest; they stay
    # separate by construction (same boundary as kb/).
    pkg = ROOT / "verification_agent" / "hypothesize"
    offenders = []
    for py in pkg.glob("*.py"):
        text = py.read_text()
        for line in text.splitlines():
            s = line.strip()
            if s.startswith(("import ", "from ")) and "verify" in s:
                offenders.append((py.name, s))
    assert not offenders, f"hypothesize must not import verify: {offenders}"
