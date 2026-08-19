"""The invariant, under test. If these fail, do not let the timers run.

An unattended engine's only protection against becoming a bullshit fountain is
that the rules are executable. These tests are that executability.
"""

from __future__ import annotations

import json

import pytest

import discovery_engine as de
import verifygate_adapter as vg


# ------------------------------------------------- eligibility is both conditions
def test_refused_riddles_are_registered_and_ineligible():
    reg = de.build_registry()
    refused = {l.name for l in reg.refused()}
    for name in ("I_bedside_witness", "II_quantum_gravity", "VIII_biosignatures"):
        assert name in refused, f"{name} must be registered as refused, not omitted"
        lane = next(l for l in reg.all() if l.name == name)
        assert lane.validated is True, "a refused riddle is still a REAL riddle"
        assert lane.oracle is None
        assert lane.eligible is False


def test_eligible_lanes_are_exactly_the_oracled_ones():
    reg = de.build_registry()
    assert {l.name for l in reg.eligible()} == {
        "contract_verification", "study001_nrr_audit", "study002_deception_probe"}


@pytest.mark.parametrize("validated,has_oracle,expected", [
    (True, True, True), (True, False, False), (False, True, False), (False, False, False)])
def test_eligibility_requires_both_conditions(validated, has_oracle, expected):
    lane = de.Lane("t", "science", validated,
                   (lambda c: de.Judgement(de.PASS)) if has_oracle else None,
                   lambda: [], "test lane")
    assert lane.eligible is expected


def test_refusals_are_logged_where_a_human_can_read_them():
    import paths
    de.run_all(de.build_registry(), dry_run=True)
    logged = {json.loads(f.read_text())["lane"] for f in paths.q_refused().glob("*.json")}
    assert {"I_bedside_witness", "II_quantum_gravity", "VIII_biosignatures"} <= logged


# ------------------------------------------- the generator never gets a vote
def test_gate_discards_the_generators_self_verdict():
    from moe_orchestrator import gate
    judged = gate({"id": "x", "self_verdict": "CONFIRMED", "confidence": 0.99,
                   "hypothesis": "anything"})
    assert "self_verdict" not in judged and "confidence" not in judged
    assert judged["gate_verdict"] != vg.CONFIRMED, (
        "a hypothesis with no runnable scenario must never be CONFIRMED")
    assert judged["gate_reason"] == "no_runnable_case"


def test_a_hypothesis_is_not_a_runnable_case():
    result = vg.verify({"id": "no-scenario", "hypothesis": "plausible words"})
    assert result.verdict == vg.INCONCLUSIVE
    assert result.available is False


# -------------------------------- an oracle that could not run cannot say PASS
def test_unavailable_oracle_is_counted_separately_and_never_queued():
    import paths

    def unavailable_oracle(_cand):
        return de.Judgement(de.INCONCLUSIVE, {"oracle_ran": False, "reason": "no forge"})

    reg = de.Registry()
    reg.register(de.Lane("stub", "verification", True, unavailable_oracle,
                         lambda: [{"id": "a"}, {"id": "b"}], "stub"))
    row = de.run_all(reg)["lanes"][0]
    assert row["oracle_unavailable"] == 2
    assert row["accepted"] == 0 and row["queued"] == []
    assert not list(paths.q_review().glob("*.json"))


def test_held_out_adversary_aborts_honestly_instead_of_passing():
    j = de.held_out_adversary_oracle({"auroc_vs_adversary": 0.99, "threshold": 0.5})
    assert j.verdict == de.INCONCLUSIVE, "a great AUROC vs a non-held-out adversary is not a pass"
    assert j.oracle_ran is False
    assert j.accepted is False


def test_degraded_generator_is_not_reported_as_finding_nothing():
    from headless import GenerationUnavailable

    def broken():
        raise GenerationUnavailable("`claude` is not on PATH")

    reg = de.Registry()
    reg.register(de.Lane("stub", "science", True, lambda c: de.Judgement(de.PASS),
                         broken, "stub"))
    row = de.run_all(reg)["lanes"][0]
    assert row["generated"] == 0
    assert row["degraded"] and "not on PATH" in row["degraded"]


# ------------------------------------------------------- queue record honesty
def test_queued_records_carry_unmeasured_blind_precision():
    import paths
    reg = de.Registry()
    reg.register(de.Lane("contract_stub", "verification", True,
                         lambda c: de.Judgement(de.CONFIRMED, {"oracle": "stub"}),
                         lambda: [{"id": "q1", "hypothesis": "h"}], "stub"))
    de.run_all(reg)
    files = list(paths.q_review().glob("*.json"))
    assert len(files) == 1
    rec = json.loads(files[0].read_text())
    assert rec["blind_precision"] == "UNMEASURED"
    assert rec["calibration_needed"]
    assert "three-field re-audit" == rec["human_step"]
    assert "host function correct" in rec["checklist"]


def test_science_pass_asks_for_an_oracle_spot_check():
    import paths
    reg = de.Registry()
    reg.register(de.Lane("sci", "science", True,
                         lambda c: de.Judgement(de.PASS, {"oracle": "stub"}),
                         lambda: [{"id": "p1"}], "stub"))
    de.run_all(reg)
    rec = json.loads(next(iter(paths.q_review().glob("*.json"))).read_text())
    assert rec["human_step"] == "spot-check the oracle's PASS"


# --------------------------------------------------------- the drafter's wall
def test_drafter_cannot_register_a_lane():
    """Structural wall: the drafter's code contains no path to lane registration.

    Checked over the parsed AST rather than the source text, so a docstring that
    merely says "never registers a lane" cannot satisfy — or break — the test.
    """
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(de.draft_riddles)))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    forbidden = {"register", "Registry", "Lane", "build_registry", "run_all"}
    assert not (names | attrs) & forbidden, (
        "the thing that proposes frontier problems must not certify their floors")


def test_validation_form_asks_for_every_corner_and_the_floor():
    assert de.RIDDLE_VALIDATION_FORM.count("[ ]") >= 7
    assert "name the oracle" in de.RIDDLE_VALIDATION_FORM


def test_rubric_pass_is_labelled_presence_floor_not_graded_scoring():
    fields = {c: True for c in de.ANDERSEN_CONTROLS}
    j = de.andersen2019_rubric(fields)
    assert j.verdict == de.PASS
    assert j.detail["oracle_maturity"] == "PRESENCE_FLOOR"
    assert de.andersen2019_rubric({}).verdict == de.FAIL
    partial = de.andersen2019_rubric({"open_circuit_blank": True})
    assert partial.verdict == de.FAIL
    assert "isotope_15N2_control" in partial.detail["controls_missing"]
