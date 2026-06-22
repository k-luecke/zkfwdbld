"""Offline tests for the verification-surface tagger and lite extractor.

These run with no network, no forge, no slither — they exercise the one piece
of M0 that encodes the agent's specialization. The M0 gate ("emit a flagged
verification surface") is meaningless if this logic is wrong, so it is the
first thing covered by tests.
"""

from pathlib import Path

from verification_agent.model.surface import tag_surfaces
from verification_agent.model.lite import extract_lite
from verification_agent.schema import SurfaceCategory

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "SurfaceSampler.sol"


def _cats(d):
    return set(d.keys())


def test_signature_surface():
    assert SurfaceCategory.SIGNATURE_PROOF.value in tag_surfaces("claimWithSig",
        callees=["ecrecover"])
    assert SurfaceCategory.SIGNATURE_PROOF.value in tag_surfaces("verifyProof")


def test_merkle_surface():
    assert SurfaceCategory.MERKLE_STATE_PROOF.value in tag_surfaces("proveStorage",
        callees=["merkleProof"])


def test_bridge_surface():
    assert SurfaceCategory.BRIDGE_INBOUND.value in tag_surfaces("relayMessage")


def test_cross_domain_via_modifier():
    tags = tag_surfaces("setStateRoot", modifiers=["onlyCrossDomain"])
    assert SurfaceCategory.CROSS_DOMAIN_AUTH.value in tags


def test_slashing_surface():
    assert SurfaceCategory.SLASHING_AVS.value in tag_surfaces("slashOperator")


def test_decoys_not_tagged_by_keywords():
    # The *keyword* tagger keys on vocabulary: generic helpers get no surface.
    assert tag_surfaces("contribute") == {}
    assert tag_surfaces("currentOwner") == {}
    assert tag_surfaces("totalSupply") == {}


def test_structural_rule_fires_on_unguarded_state_change():
    from verification_agent.model.surface import tag_structural, is_auth_modifier
    from verification_agent.schema import SurfaceCategory

    # receiveFromBridge-shaped: reachable, makes external calls, no modifier.
    t = tag_structural(is_entry_point=True, writes_state=False,
                       makes_external_calls=True, modifiers=[])
    assert SurfaceCategory.UNGUARDED_ENTRYPOINT.value in t

    # Guarded (onlyOwner / onlyRouter / onlyUtb) -> excluded.
    assert is_auth_modifier("onlyOwner") and is_auth_modifier("onlyRouter")
    assert is_auth_modifier("onlyUtb") and is_auth_modifier("onlyCrossDomain")
    assert tag_structural(is_entry_point=True, writes_state=True,
                          makes_external_calls=True, modifiers=["onlyOwner"]) == {}

    # view/pure with no effect -> excluded.
    assert tag_structural(is_entry_point=True, writes_state=False,
                          makes_external_calls=False, modifiers=[]) == {}
    # not an entry point -> excluded.
    assert tag_structural(is_entry_point=False, writes_state=True,
                          makes_external_calls=True, modifiers=[]) == {}


def test_lite_extractor_over_fixture():
    contracts, _storage, entry_points = extract_lite([FIXTURE])
    by_name = {f.name: f for f in entry_points}
    # Entry points only (internal/private excluded).
    assert {"claimWithSig", "verifyProof", "proveStorage", "relayMessage",
            "setStateRoot", "slashOperator", "contribute", "currentOwner"} <= set(by_name)

    tagged = {n for n, f in by_name.items() if f.surfaces}
    # Every keyword-priority function is on the surface.
    assert {"claimWithSig", "verifyProof", "proveStorage", "relayMessage",
            "setStateRoot", "slashOperator"} <= tagged

    # contribute() has no verification vocabulary but writes state with no auth
    # modifier: caught structurally, on behavior, not name.
    assert by_name["contribute"].structural_priority is True
    assert "unguarded_privileged_entrypoint" in by_name["contribute"].surfaces

    # currentOwner() is a view with no effect -> stays off the surface entirely.
    assert by_name["currentOwner"].surfaces == []
    assert by_name["currentOwner"].structural_priority is False

    # Sanity: the contract itself was recognized.
    assert any(c.name == "SurfaceSampler" for c in contracts)
