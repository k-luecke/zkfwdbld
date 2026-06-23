"""Offline tests for Move A (shape-fit screen) + Move B (judged-findings parse).

Move A: the codified Kelp lesson — shape-fit keys on Seer-pathability, so Decent
scores HIGH and Kelp scores LOW from code structure alone. Move B: parse a REAL
Code4rena report into the answer-key format, with the BlindRunner wall intact.
No network/forge — Seer is structural over the committed M0 models; the report is
a saved real-content fixture.
"""

import json
from pathlib import Path

from verification_agent.screen import ShapeScreener
from verification_agent.screen.findings import parse_c4_report, to_answer_key

ROOT = Path(__file__).resolve().parents[1]
DECENT = ROOT / "examples" / "2024-01-decent.model.json"
KELP = ROOT / "examples" / "2023-11-kelp.model.json"
REPORT_FIXTURE = ROOT / "fixtures" / "c4_report_sample.md"


def _model(p):
    return json.loads(Path(p).read_text())


# --- Move A: shape-fit ------------------------------------------------------

def test_decent_scores_high_shape_fit():
    rep = ShapeScreener().screen(_model(DECENT), target="decent")
    # Decent contains the alt-entrypoint shape (M-03): Seer paths it.
    assert rep.band == "HIGH"
    assert rep.pathable_pairs >= 1
    assert any(e["attack_entrypoint"] == "receiveFromBridge"
               for e in rep.pathable_evidence)


def test_kelp_scores_low_shape_fit():
    rep = ShapeScreener().screen(_model(KELP), target="kelp")
    # The Kelp lesson: claimed-rule candidates exist but Seer paths NONE -> LOW.
    assert rep.band == "LOW"
    assert rep.pathable_pairs == 0
    assert rep.candidate_violations >= 1   # it has weak candidates, just not pathable


def test_shape_fit_orders_decent_above_kelp():
    s = ShapeScreener()
    assert s.screen(_model(DECENT)).shape_fit > s.screen(_model(KELP)).shape_fit


def test_screener_uses_no_findings_only_structure():
    # The screen must derive everything from the model; it must not IMPORT the
    # findings/answer-key data (that would let it rank on judged outcomes).
    src = (ROOT / "verification_agent" / "screen" / "shape.py").read_text()
    for line in src.splitlines():
        s = line.strip()
        if s.startswith(("import ", "from ")):
            low = s.lower()
            assert "findings" not in low and "answer_key" not in low
            assert "contests" not in low and "answer_keys" not in low


# --- Move B: judged-findings parse + the wall -------------------------------

def test_parses_real_report_ids_and_severity():
    findings = parse_c4_report(REPORT_FIXTURE.read_text())
    by_id = {f.id: f for f in findings}
    # All 9 judged Decent findings, exact ids + severities.
    assert set(by_id) == {"H-01", "H-02", "H-03", "H-04",
                          "M-01", "M-02", "M-03", "M-04", "M-05"}
    assert by_id["H-01"].severity == "High"
    assert by_id["M-03"].severity == "Medium"


def test_parser_extracts_host_from_title_when_present():
    findings = {f.id: f for f in parse_c4_report(REPORT_FIXTURE.read_text())}
    # M-03's title names UTB:receiveFromBridge -> UTB.receiveFromBridge.
    assert "UTB.receiveFromBridge" in findings["M-03"].hosts
    # M-02's title names DecentEthRouter::bridgeWithPayload().
    assert "DecentEthRouter.bridgeWithPayload" in findings["M-02"].hosts


def test_answer_key_tuple_shape_matches_scorer_format():
    findings = parse_c4_report(REPORT_FIXTURE.read_text())
    rows = to_answer_key(findings)
    # (id, title, mechanism, severity, hosts) — the ANSWER_KEYS row format.
    for fid, title, mechanism, severity, hosts in rows:
        assert fid and title and severity in ("High", "Medium")
        assert isinstance(hosts, list)


def test_blindrunner_wall_does_not_read_answer_keys():
    # Move B writes answer keys; the BlindRunner must still not read them.
    runner = (ROOT / "verification_agent" / "backtest" / "runner.py").read_text()
    for line in runner.splitlines():
        s = line.strip()
        if s.startswith(("import ", "from ")):
            assert "ANSWER_KEYS" not in s and "findings" not in s and "contests" not in s
