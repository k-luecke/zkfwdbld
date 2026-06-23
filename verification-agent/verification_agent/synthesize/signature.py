"""M4.5 signature synthesis — construct a valid signature from the scheme, not the answer.

The deploy-graph ledger showed the real wall: the honest Control needs a VALID
signature, and hand-supplying it is the signature-mile version of faking the catch.
This module CONSTRUCTS one — by reading the protocol's verification code, detecting
which signing scheme it checks, and emitting the matching Solidity signer. It never
copies an existing signature and never reads the answer out of the test.

Discipline:
  * CONSTRUCT, NEVER EXTRACT — the emitted signer rebuilds the digest the verifier
    checks and `vm.sign`s it with the fixture key. No signature bytes are lifted.
  * CONSTRUCTION GENERAL, INPUTS LOCAL — scheme detection + signer emission carry no
    protocol literal (asserted by a test). Only the fixture key and the message
    preimage are scenario-local, supplied by the caller.
  * WRONG SIG FAILS LOUDLY — if detection is wrong, the digest is wrong, recovery
    misses the signer, and the gate's Control phase reverts (MALFORMED_CONTROL).
    Nothing here catches or retries.

Scheme detection keys on the verifier's own structure:
  * EIP-712  if it builds a digest with the "\\x19\\x01" prefix / a DOMAIN_SEPARATOR.
  * EIP-191  if it uses the "\\x19Ethereum Signed Message" personal-sign banner
             over keccak256(preimage).
  * RAW      a bare ecrecover over keccak256(preimage) with no prefix.

State label: IMPLEMENTED (EIP-191 / RAW over a bytes preimage). EIP-712 typed-data
digest construction is detected but not emitted — see `transferability` note.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class SigScheme(str, Enum):
    EIP712 = "eip712_typed_data"
    EIP191 = "eip191_personal_sign"
    RAW = "raw_ecrecover"
    UNKNOWN = "unknown"


@dataclass
class DetectedScheme:
    scheme: SigScheme
    banner: str = ""          # the personal-sign banner literal, extracted verbatim
    sig_layout: str = "rsv"   # byte order the verifier's split expects
    evidence: str = ""        # the verifier substring that triggered detection

    @property
    def emittable(self) -> bool:
        # We can emit a signer for schemes that sign a digest over a bytes preimage.
        return self.scheme in (SigScheme.EIP191, SigScheme.RAW)


# A personal-sign banner: \x19 + "Ethereum Signed Message:\n" + a length. Matched
# in the verifier's *source text* (escaped form), then emitted verbatim.
_BANNER_RE = re.compile(r'\\x19Ethereum Signed Message:\\n\d+')
# Signature split order: detect whether v is read first (vrs) or last (rsv).
_SPLIT_RE = re.compile(r"mload\(add\(signature,\s*(\d+)\)\)")


def detect_scheme(verifier_src: str) -> DetectedScheme:
    """Detect the signing scheme a verification function checks, from its source."""
    s = verifier_src
    low = s.lower()
    if "\\x19\\x01" in s or "domain_separator" in low or "eip712" in low:
        return DetectedScheme(SigScheme.EIP712, evidence="EIP-712 domain prefix")
    m = _BANNER_RE.search(s)
    if m:
        return DetectedScheme(SigScheme.EIP191, banner=m.group(0),
                              sig_layout=_split_layout(s),
                              evidence=m.group(0))
    if "ecrecover" in low and "keccak256" in low:
        return DetectedScheme(SigScheme.RAW, sig_layout=_split_layout(s),
                              evidence="ecrecover over keccak256(preimage)")
    return DetectedScheme(SigScheme.UNKNOWN)


def _split_layout(src: str) -> str:
    """Infer (r,s,v) vs (v,r,s) packing from the verifier's splitSignature offsets.

    Standard packing reads r@32, s@64, v@96 -> "rsv". If v is read at offset 32,
    the verifier expects v first -> "vrs".
    """
    offs = _SPLIT_RE.findall(src)
    # Heuristic: the byte() extraction of v sits at the largest offset for rsv.
    if "byte(0, mload(add(signature, 32)))".replace(" ", "") in src.replace(" ", ""):
        return "vrs"
    return "rsv"


def render_signer(scheme: DetectedScheme, helper: str = "_synthSign") -> str:
    """Emit a Solidity helper that CONSTRUCTS a signature for the detected scheme.

    Signature: `helper(uint256 pk, bytes memory preimage) -> bytes`. The caller
    supplies the fixture key and the message preimage (scenario-local). Nothing
    protocol-specific is baked in beyond the scheme the verifier itself uses.
    """
    if not scheme.emittable:
        raise ValueError(f"no signer emitter for scheme {scheme.scheme.value}")
    pack = "abi.encodePacked(r, s, v)" if scheme.sig_layout == "rsv" \
        else "abi.encodePacked(v, r, s)"
    if scheme.scheme is SigScheme.EIP191:
        banner = scheme.banner or r"\x19Ethereum Signed Message:\n32"
        digest = (f'keccak256(abi.encodePacked("{banner}", '
                  f"keccak256(preimage)))")
    else:  # RAW
        digest = "keccak256(preimage)"
    return (
        f"    // MACHINE-SYNTHESIZED signer for scheme={scheme.scheme.value}\n"
        f"    // (digest reconstructed from the verifier; signed with the fixture key)\n"
        f"    function {helper}(uint256 pk, bytes memory preimage)\n"
        f"        internal view returns (bytes memory)\n"
        f"    {{\n"
        f"        bytes32 digest = {digest};\n"
        f"        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, digest);\n"
        f"        return {pack};\n"
        f"    }}"
    )


def transferability(scheme: DetectedScheme) -> str:
    """Honest note on whether this generalizes to the EIP-712 permit frontier."""
    return (
        "The detect->emit frame is general over schemes that sign a digest of a "
        "bytes preimage (EIP-191 / raw ecrecover): only the digest expression "
        "changes. It does NOT yet cover EIP-712 typed data, whose digest is built "
        "from a domain separator + typehash + per-field struct encoding (not an "
        "opaque bytes preimage). EIP-712 is DETECTED but not EMITTED, so the "
        "permit/signature-scope class needs a typed-data digest builder, not just "
        "this signer. The abstraction transfers in shape, not yet in coverage."
    )
