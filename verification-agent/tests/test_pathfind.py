"""Offline tests for M4 path backends.

The acceptance test for M4 is reproduce-before-discover: can Seer independently
rediscover the known M-03 path from the M0 model alone? Plus the coverage map's
honesty and the backend wall (pathfind never imports the gate). No network/forge.
"""

import json
from pathlib import Path

from verification_agent.hypothesize import HypothesisEngine
from verification_agent.pathfind import (
    PathOrchestrator,
    PathStatus,
    SeerStructuralBackend,
)

ROOT = Path(__file__).resolve().parents[1]
DECENT = ROOT / "examples" / "2024-01-decent.model.json"


def _model():
    return json.loads(DECENT.read_text())


def _hyps(model):
    return HypothesisEngine().run(model)


def test_seer_rediscovers_m03_path():
    model = _model()
    seer = SeerStructuralBackend()
    # From ANY UTB access-control hypothesis, Seer must pinpoint receiveFromBridge
    # bypassing retrieveAndCollectFees — the M-03 mechanism, from the model alone.
    hit = None
    for h in _hyps(model):
        if h.target_contract == "UTB" and h.root_cause == "access-control":
            r = seer.find_path(h, model)
            if r.found and r.attack_entrypoint == "receiveFromBridge":
                hit = r
                break
    assert hit is not None, "Seer failed to rediscover the M-03 path"
    assert "_swapAndExecute" in hit.reaches
    assert hit.guard_bypassed == "retrieveAndCollectFees"
    assert hit.gate_binding == "DecentReceiveFromBridgeBypass"


def test_seer_out_of_scope_for_non_reachability_mechanism():
    model = _model()
    seer = SeerStructuralBackend()
    # A signature-verification hypothesis comes from the structural generator
    # (protocol-aware mode maps claimed-rule violations to access-control only).
    sig = [h for h in HypothesisEngine().run(model, protocol_aware=False)
           if h.root_cause == "signature-verification"]
    assert sig
    r = seer.find_path(sig[0], model)
    # The structural backend honestly declines mechanisms it doesn't reason about.
    assert r.status is PathStatus.OUT_OF_SCOPE


def test_orchestrator_coverage_map_is_honest():
    model = _model()
    report = PathOrchestrator().run(_hyps(model), model, run_external=False)
    names = {b["name"] for b in report["backends"]}
    assert {"seer-structural", "medusa", "halmos"} <= names
    # Seer found the access-control mechanism; the map records it per-mechanism.
    cov = report["coverage"]["by_mechanism"]
    assert "seer-structural" in cov.get("access-control", {}).get("found_by", [])
    # A gate-bound discovered path exists for the loop's handoff.
    assert any(r["gate_binding"] for r in report["found_paths"])


def test_pathfind_does_not_import_the_gate():
    # Same wall as kb/ and hypothesize/: discovery never imports verification.
    pkg = ROOT / "verification_agent" / "pathfind"
    offenders = []
    for py in pkg.glob("*.py"):
        for line in py.read_text().splitlines():
            s = line.strip()
            if s.startswith(("import ", "from ")) and "verify" in s:
                offenders.append((py.name, s))
    assert not offenders, f"pathfind must not import verify: {offenders}"
