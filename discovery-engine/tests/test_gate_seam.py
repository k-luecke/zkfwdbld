"""The gate seam: verdict projection, prerequisite honesty, and headless parsing."""

from __future__ import annotations

import json

import pytest

import verifygate_adapter as vg
from headless import GenerationUnavailable, parse_records


# ------------------------------------------------------- verdict projection
@pytest.mark.parametrize("raw,expected", [
    ("CONFIRMED", vg.CONFIRMED),
    ("REJECTED_MALFORMED_BASELINE", vg.REFUTED),
    ("REJECTED_MALFORMED_CONTROL", vg.REFUTED),
    ("REJECTED_MALFORMED_CONTROL_REVERT", vg.REFUTED),
    ("REJECTED_ATTACK_REVERTED", vg.REFUTED),
    ("REJECTED_INVARIANT_INTACT", vg.REFUTED),
    ("NO_VERDICT", vg.INCONCLUSIVE),
])
def test_every_harness_verdict_projects_to_one_of_three_words(raw, expected):
    verdict, reason = vg._project(raw)
    assert verdict == expected
    assert reason


def test_projection_covers_the_harnesss_whole_taxonomy():
    """If the harness grows a verdict, this test fails instead of silently mapping it."""
    harness_verdicts = _harness_verdict_values()
    if harness_verdicts is None:
        pytest.skip("verification_agent not importable here")
    for raw in harness_verdicts:
        verdict, _ = vg._project(raw)
        assert verdict in (vg.CONFIRMED, vg.REFUTED, vg.INCONCLUSIVE)
        if raw != "CONFIRMED":
            assert verdict != vg.CONFIRMED, f"{raw} must never read as CONFIRMED"


def test_rejection_reason_is_preserved_not_flattened():
    _, reason = vg._project("REJECTED_INVARIANT_INTACT")
    assert "invariant_intact" in reason


def _harness_verdict_values():
    if vg._import_harness() is None:
        return None
    from verification_agent.verify.gate import Verdict
    return [v.value for v in Verdict]


# -------------------------------------------------- prerequisites are honest
def test_preflight_names_what_is_missing_rather_than_guessing():
    missing = vg.preflight()
    assert isinstance(missing, list)
    if vg.forge_path() is None:
        assert any("forge" in m for m in missing)


def test_verify_without_prerequisites_is_inconclusive_never_confirmed(monkeypatch):
    monkeypatch.setattr(vg, "preflight", lambda: ["forge (Foundry) not installed"])
    result = vg.verify({"target_repo": "/nonexistent", "contract_name": "C"})
    assert result.verdict == vg.INCONCLUSIVE
    assert result.available is False
    assert result.reason == "oracle_unavailable"


def test_selftest_reports_unavailable_instead_of_ok(monkeypatch):
    monkeypatch.setattr(vg, "preflight", lambda: ["forge missing"])
    out = vg.selftest("/nonexistent")
    assert out["ok"] is False and out["reason"] == "oracle_unavailable"


def test_missing_target_is_distinguished_from_missing_tooling(monkeypatch):
    monkeypatch.setattr(vg, "preflight", lambda: [])
    result = vg.verify({"target_repo": "/definitely/not/here", "contract_name": "C"})
    assert result.reason == "target_missing"


# --------------------------------------------------------- headless parsing
def test_parses_a_plain_json_list_result():
    envelope = json.dumps({"result": json.dumps([{"id": "a"}, {"id": "b"}])})
    assert parse_records(envelope) == [{"id": "a"}, {"id": "b"}]


def test_parses_a_fenced_json_block():
    envelope = json.dumps({"result": "```json\n[{\"id\": \"a\"}]\n```"})
    assert parse_records(envelope) == [{"id": "a"}]


def test_unwraps_a_keyed_object():
    envelope = json.dumps({"result": json.dumps({"hypotheses": [{"id": "a"}]})})
    assert parse_records(envelope) == [{"id": "a"}]


def test_a_single_object_becomes_one_record():
    envelope = json.dumps({"result": json.dumps({"id": "solo"})})
    assert parse_records(envelope) == [{"id": "solo"}]


@pytest.mark.parametrize("stdout", [
    "not json at all",
    json.dumps({"result": "I looked at the repo and found three issues."}),
    json.dumps({"result": json.dumps(["a string", "another"])}),
    json.dumps({"result": json.dumps(42)}),
])
def test_unparseable_output_raises_instead_of_looking_like_no_findings(stdout):
    with pytest.raises(GenerationUnavailable):
        parse_records(stdout)


def test_an_empty_list_is_a_legitimate_no_findings_result():
    assert parse_records(json.dumps({"result": "[]"})) == []
