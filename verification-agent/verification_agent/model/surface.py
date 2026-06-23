"""Verification-surface tagger — the specialization filter.

This is the one piece of M0 that encodes *what this agent is for*. Every other
M0 component is generic plumbing (clone, compile, run Slither). This module
decides which functions sit on the verification / reachability / cross-chain /
ZK surface that the agent prioritizes and that commodity scanners miss.

The tagger is deliberately conservative and *evidence-producing*: it never just
returns a boolean, it returns the substrings that triggered each tag so a human
operator can audit (and correct) the heuristic. False positives here are cheap
(a function gets extra attention); false negatives are expensive (a real bug
class gets deprioritized), so the keyword sets lean toward recall.

State label: IMPLEMENTED (heuristic; precision improves via the LEARN loop).
"""

from __future__ import annotations

import re

from ..schema import SurfaceCategory

# Each category maps to keyword fragments matched case-insensitively against a
# function's name, its called-function names, and (when available) its source
# body. Fragments are matched as substrings on a normalized lowercase string,
# except those wrapped as raw regex via the (..)-prefixed form below.
_KEYWORDS: dict[SurfaceCategory, list[str]] = {
    SurfaceCategory.SIGNATURE_PROOF: [
        "ecrecover", "recover", "isvalidsignature", "_1271", "eip1271",
        "erc1271", "signature", "signed", "sigutil", "verifysig", "ecdsa",
        "schnorr", "bls", "pairing", "g1point", "g2point", "blssig",
        "verifyproof", "verify_proof", "groth16", "plonk", "snark", "zkproof",
        "verifyingkey", "validateproof", "checkproof", "permit", "digest",
    ],
    SurfaceCategory.MERKLE_STATE_PROOF: [
        "merkle", "merkleproof", "computeroot", "_root", "stateroot",
        "storageproof", "accountproof", "rlp", "mpt", "trie", "patricia",
        "verifyinclusion", "verifymembership", "proveaccount", "provestorage",
        "checkpointroot", "blockhash", "headerroot", "receiptroot", "txroot",
    ],
    SurfaceCategory.BRIDGE_INBOUND: [
        "relaymessage", "receivemessage", "executemessage", "processmessage",
        "_lzreceive", "lzreceive", "nonblockinglzreceive", "onmessage",
        "ccipreceive", "handle", "deliver", "commitheader", "submitheader",
        "finalizewithdrawal", "provewithdrawal", "claim", "mint", "deposit",
        "inbound", "consumemessage", "anyexecute", "wormholereceive",
    ],
    SurfaceCategory.CROSS_DOMAIN_AUTH: [
        "xdomainmessagesender", "crossdomainmessenger", "oncrossdomain",
        "onlycrossdomain", "l1sender", "l2sender", "otherbridge",
        "messenger", "remotechainid", "sourcechainid", "trustedremote",
        "peer", "endpoint", "onlyendpoint", "onlymessenger", "originsender",
    ],
    SurfaceCategory.SLASHING_AVS: [
        "slash", "slashing", "freeze", "jail", "avs", "eigen", "operatorset",
        "registeroperator", "deregisteroperator", "delegate", "undelegate",
        "withdrawalqueue", "checkpoint", "stakeregistry", "quorum",
        "servicemanager", "allocate", "deallocate", "magnitude", "burnshares",
    ],
}

# A few fragments are short enough to collide with unrelated English/Solidity
# words ("trie" inside "entries", "mpt" inside "attempt", "avs" inside
# "savings"). For just these we require a word boundary. Everything else is a
# plain substring match — recall-biased, because a missed surface is far more
# expensive than an over-tagged one.
_BOUNDARY_REQUIRED = {
    "trie", "mpt", "rlp", "avs", "peer", "_root", "jail",
}


def _matches(fragment: str, haystack: str) -> bool:
    if fragment in _BOUNDARY_REQUIRED:
        return re.search(rf"(?<![a-z0-9]){re.escape(fragment)}(?![a-z0-9])", haystack) is not None
    return fragment in haystack


# Modifier-name fragments that indicate the function restricts its callers to a
# trusted set (access control / verification gate). A function carrying one of
# these is treated as guarded and is NOT flagged by the structural rule.
_AUTH_MODIFIER_HINTS = (
    "auth", "owner", "admin", "gov", "role", "restrict", "permission",
    "guard", "keeper", "whitelist", "operator", "manager", "controller",
)


def is_auth_modifier(name: str) -> bool:
    """Heuristic: does this modifier name gate the caller?

    ``only*`` is the dominant Solidity convention (onlyOwner, onlyRouter,
    onlyMessenger, onlyCrossDomain, onlyUtb), plus a set of access-control word
    stems. Deliberately broad: a missed auth modifier over-flags (cheap), a
    falsely-claimed one under-flags a real bug (expensive).
    """
    n = (name or "").lower()
    if n.startswith("only"):
        return True
    return any(h in n for h in _AUTH_MODIFIER_HINTS)


def tag_structural(
    *,
    is_entry_point: bool,
    writes_state: bool,
    makes_external_calls: bool,
    modifiers: list[str] | None = None,
    is_state_mutating: bool = True,
) -> dict[str, list[str]]:
    """Name-independent priority rule (the recall fix).

    Flags an externally reachable function that drives a privileged effect
    (writes state OR makes external/low-level calls) yet carries no auth
    modifier. This is the M-03 mechanism — "privileged entrypoint reachable
    without the auth modifier" — and it fires on behavior, so an oddly-named
    function like ``receiveFromBridge`` is caught even though its name dodges
    every keyword. Note the same structural features are what M2 retrieves on,
    so the entry filter and the knowledge base align on mechanism.
    """
    if not is_entry_point:
        return {}
    if not is_state_mutating:
        return {}  # view/pure: a staticcall is not a privileged effect
    if any(is_auth_modifier(m) for m in (modifiers or [])):
        return {}  # guarded: deliberately excluded to keep precision
    if not (writes_state or makes_external_calls):
        return {}  # inert: nothing privileged to reach
    evidence = ["external-entrypoint"]
    if writes_state:
        evidence.append("writes-state")
    if makes_external_calls:
        evidence.append("external-call")
    evidence.append("no-auth-modifier")
    return {SurfaceCategory.UNGUARDED_ENTRYPOINT.value: evidence}


def tag_surfaces(
    function_name: str,
    callees: list[str] | None = None,
    source_body: str | None = None,
    modifiers: list[str] | None = None,
) -> dict[str, list[str]]:
    """Return ``{category_value: [evidence, ...]}`` for every surface hit.

    ``callees`` and ``modifiers`` are folded into the searchable text because a
    bridge handler is often only recognizable by *what it calls* (e.g. a plain
    ``execute`` that invokes ``xDomainMessageSender``), and cross-domain auth is
    frequently expressed as a modifier (``onlyMessenger``).
    """
    parts = [function_name or ""]
    parts.extend(callees or [])
    parts.extend(modifiers or [])
    name_callee_blob = " ".join(parts).lower()
    body_blob = (source_body or "").lower()

    result: dict[str, list[str]] = {}
    for category, fragments in _KEYWORDS.items():
        evidence: list[str] = []
        for frag in fragments:
            # Name/callee/modifier matches are high-signal; body-only matches
            # are weaker but still worth surfacing with a marker.
            if _matches(frag, name_callee_blob):
                evidence.append(frag)
            elif body_blob and _matches(frag, body_blob):
                evidence.append(f"{frag}(body)")
        if evidence:
            # De-dup while preserving order.
            seen: set[str] = set()
            ordered = [e for e in evidence if not (e in seen or seen.add(e))]
            result[category.value] = ordered
    return result
