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


def test_decoys_not_tagged():
    # Generic accounting / view helpers must stay off the priority surface.
    assert tag_surfaces("contribute") == {}
    assert tag_surfaces("currentOwner") == {}
    assert tag_surfaces("totalSupply") == {}


def test_lite_extractor_over_fixture():
    contracts, _storage, entry_points = extract_lite([FIXTURE])
    names = {f.name for f in entry_points}
    # Entry points only (internal/private excluded).
    assert {"claimWithSig", "verifyProof", "proveStorage", "relayMessage",
            "setStateRoot", "slashOperator", "contribute", "currentOwner"} <= names

    tagged = {f.name for f in entry_points if f.surfaces}
    # Every priority function is on the surface; both decoys are not.
    assert {"claimWithSig", "verifyProof", "proveStorage", "relayMessage",
            "setStateRoot", "slashOperator"} <= tagged
    assert "contribute" not in tagged
    assert "currentOwner" not in tagged

    # Sanity: the contract itself was recognized.
    assert any(c.name == "SurfaceSampler" for c in contracts)
