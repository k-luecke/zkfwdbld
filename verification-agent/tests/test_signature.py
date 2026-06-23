"""Offline tests for M4.5 signature synthesis (no forge needed).

The forge-executed proof — the synthesized signer makes Control pass and the gate
reaches CONFIRMED, while a WRONG scheme reverts Control (MALFORMED_CONTROL) — is the
recorded run in examples/m45_signature_decent.txt. These tests pin the Python side:
scheme detection from a verifier's source, target-agnostic emission (CONSTRUCT not
EXTRACT), and the wall the abstraction hits at EIP-712.
"""

from pathlib import Path

from verification_agent.synthesize.signature import (
    DetectedScheme,
    SigScheme,
    detect_scheme,
    render_signer,
    transferability,
)

ROOT = Path(__file__).resolve().parents[1]

# A minimal EIP-191 personal-sign verifier (mirrors the shape of the real one,
# without any protocol identifiers — detection keys on the scheme, not the name).
_EIP191_SRC = r'''
    string constant BANNER = "\x19Ethereum Signed Message:\n32";
    function verify(bytes memory packedInfo, bytes memory signature) public view {
        bytes32 h = keccak256(abi.encodePacked(BANNER, keccak256(packedInfo)));
        (bytes32 r, bytes32 s, uint8 v) = splitSignature(signature);
        require(ecrecover(h, v, r, s) == signer, "Wrong signature");
    }
'''

_EIP712_SRC = r'''
    bytes32 public DOMAIN_SEPARATOR;
    function permit(...) external {
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR, structHash));
        require(ecrecover(digest, v, r, s) == owner, "bad sig");
    }
'''


def test_detects_eip191_and_extracts_banner_verbatim():
    d = detect_scheme(_EIP191_SRC)
    assert d.scheme is SigScheme.EIP191
    # The banner is read from the verifier source, not hardcoded by scheme name.
    assert d.banner == r"\x19Ethereum Signed Message:\n32"
    assert d.emittable


def test_detects_eip712_but_does_not_emit():
    d = detect_scheme(_EIP712_SRC)
    assert d.scheme is SigScheme.EIP712
    assert not d.emittable  # detected, honestly not yet emittable


def test_rendered_signer_reconstructs_the_digest_and_signs_with_fixture_key():
    d = detect_scheme(_EIP191_SRC)
    sol = render_signer(d)
    # CONSTRUCT: the signer rebuilds the verifier's digest and vm.signs it.
    assert "keccak256(abi.encodePacked(" in sol
    assert "keccak256(preimage)" in sol
    assert "vm.sign(pk, digest)" in sol
    # standard r,s,v packing for this layout
    assert "abi.encodePacked(r, s, v)" in sol
    # It takes the fixture key + the message preimage as inputs (scenario-local).
    assert "uint256 pk" in sol and "bytes memory preimage" in sol


def test_eip712_render_refuses_rather_than_guesses():
    d = detect_scheme(_EIP712_SRC)
    try:
        render_signer(d)
    except ValueError:
        return
    raise AssertionError("EIP-712 should refuse to emit, not silently guess")


def test_signer_source_is_target_agnostic_no_protocol_literals():
    # CONSTRUCTION GENERAL: the synthesizer source must carry no protocol identifier,
    # or a digest could be smuggled rather than derived from the scheme.
    src = (ROOT / "verification_agent" / "synthesize" / "signature.py").read_text().lower()
    for forbidden in ("decent", "utb", "feecollector", "collectfees", "centrifuge"):
        assert forbidden not in src


def test_transferability_note_is_honest_about_eip712():
    note = transferability(detect_scheme(_EIP191_SRC)).lower()
    assert "eip-712" in note or "eip712" in note
    assert "not yet" in note or "does not" in note


def test_synthesis_logic_modules_do_not_import_verify():
    # The wall: synthesis LOGIC (scheme detection, deploy-graph, templates, the
    # synthesizer) must not import verify/ — it produces gate INPUTS, it cannot
    # influence the verdict. Only runner.py (orchestration) may touch verify, and
    # only the Verdict vocabulary / marker parser / env helper — never a
    # verdict-deciding path (the verdict is decided on-chain, byte-for-byte).
    pkg = ROOT / "verification_agent" / "synthesize"
    logic = {"signature.py", "deploygraph.py", "synthesizer.py", "templates.py", "schema.py"}
    offenders = []
    for py in pkg.glob("*.py"):
        if py.name not in logic:
            continue
        for line in py.read_text().splitlines():
            s = line.strip()
            if s.startswith(("import ", "from ")) and "verify" in s:
                offenders.append((py.name, s))
    assert not offenders, f"synthesis logic must not import verify: {offenders}"

    # The runner is allowed verify imports, but never the harness's verdict path.
    runner = (pkg / "runner.py").read_text()
    assert "import VerifyHarness" not in runner and "VerifyHarness(" not in runner
