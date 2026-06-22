"""Generate the lane-curated KB corpus JSONL files.

Source of truth for the corpus. Run to (re)generate:
    python tools/build_corpus.py

Curation bias is deliberate: verification / cross-chain / ZK mechanisms only.
A smaller corpus that retrieves precisely beats a giant one that retrieves
noise. Each entry is mechanism-structured so retrieval keys on bug-class, not
vocabulary. Provenance is honest: OAK_TAXONOMY entries are taxonomy (no contest
claim); CONTEST_FINDING and PUBLIC_INCIDENT entries name a real, public source.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "verification_agent" / "kb" / "data"

# Surface tags mirror M0's SurfaceCategory values.
SIG = "signature_proof_verification"
MERKLE = "merkle_state_proof"
BRIDGE = "bridge_inbound_handler"
XDOMAIN = "cross_domain_auth"
SLASH = "slashing_avs_state"


# ---------------------------------------------------------------------------
# OAK taxonomy — "what kinds of attacks exist on this surface" (the scaffold).
# ---------------------------------------------------------------------------
OAK = [
    dict(
        id="oak.access.alt-entrypoint-bypass",
        bug_class="alt-entrypoint-auth-bypass",
        root_cause_category="access-control",
        invariant_violated="access-control-consistency",
        surfaces=[BRIDGE, XDOMAIN],
        entrypoint_shape="public fn that reaches a privileged internal action via an alternate path, skipping the validation/modifier the primary path enforces",
        title="Privileged action reachable through an unguarded alternate entrypoint",
        mechanism="A privileged internal routine is invoked by a public function that omits the access-control / fee / signature checks applied on the canonical entrypoints, so anyone reaches the action directly and bypasses verification.",
        mitigation="Apply the same auth/verification modifier to every entrypoint that can reach the privileged action; restrict internal-only callers.",
        tags=["modifier", "bypass", "unprotected", "internal reachable"],
    ),
    dict(
        id="oak.access.missing-modifier",
        bug_class="missing-auth-on-privileged-entrypoint",
        root_cause_category="access-control",
        invariant_violated="access-control-consistency",
        surfaces=[XDOMAIN, BRIDGE],
        entrypoint_shape="external state-changing fn with no owner/role/caller check",
        title="Privileged setter/handler missing access control",
        mechanism="A configuration setter or handler that should be owner/role gated has no modifier, letting anyone change trusted state (router, verifier set, peer).",
        mitigation="Add onlyOwner/role checks; validate msg.sender against expected cross-domain caller.",
        tags=["setter", "onlyOwner", "config"],
    ),
    dict(
        id="oak.sig.no-replay-protection",
        bug_class="signature-replay",
        root_cause_category="replay",
        invariant_violated="replay-resistance",
        surfaces=[SIG],
        entrypoint_shape="signature-gated fn whose signed digest lacks nonce/chainId/deadline",
        title="Signature replayable (no nonce / chainId / deadline)",
        mechanism="The signed message omits a nonce, chain id, or expiry, so a captured signature is replayable on the same or another chain.",
        mitigation="Bind nonce, chainId and deadline into the signed digest; track consumed nonces.",
        tags=["nonce", "deadline", "cross-chain replay", "EIP-712"],
    ),
    dict(
        id="oak.sig.ecrecover-zero",
        bug_class="ecrecover-returns-zero-accepted",
        root_cause_category="signature-verification",
        invariant_violated="signature-authenticity",
        surfaces=[SIG],
        entrypoint_shape="ecrecover result compared to a signer that may be uninitialized (zero)",
        title="ecrecover zero-address accepted as valid signer",
        mechanism="ecrecover returns address(0) on malformed input; if the configured signer is unset (zero) or the zero return is not rejected, a malformed signature authenticates.",
        mitigation="Require recovered != address(0) and signer != address(0); prefer OZ ECDSA.",
        tags=["address(0)", "uninitialized signer"],
    ),
    dict(
        id="oak.sig.unbound-params",
        bug_class="signed-digest-not-bound-to-params",
        root_cause_category="signature-verification",
        invariant_violated="message-boundary-integrity",
        surfaces=[SIG],
        entrypoint_shape="signature validates a packed blob that excludes the security-critical params actually used",
        title="Signature does not cover all security-critical parameters",
        mechanism="The verified digest is computed over a subset of inputs; parameters that drive the privileged effect are passed separately and never bound, so they can be swapped after signing.",
        mitigation="Hash every security-critical parameter into the signed digest.",
        tags=["packedInfo", "decoupled params"],
    ),
    dict(
        id="oak.sig.malleable",
        bug_class="signature-malleability",
        root_cause_category="signature-verification",
        invariant_violated="replay-resistance",
        surfaces=[SIG],
        entrypoint_shape="raw ecrecover without low-s / single-use enforcement",
        title="ECDSA signature malleability",
        mechanism="High-s/low-s duality yields a second valid signature for the same message, defeating signature-as-id replay guards.",
        mitigation="Enforce low-s (EIP-2) or track message hashes, not signatures.",
        tags=["low-s", "malleable"],
    ),
    dict(
        id="oak.merkle.bad-root-binding",
        bug_class="proof-verified-against-bad-root",
        root_cause_category="proof-forgery",
        invariant_violated="proof-soundness",
        surfaces=[MERKLE, BRIDGE],
        entrypoint_shape="inclusion proof checked against a root that is attacker-influenced, stale, or uninitialized",
        title="Merkle/state proof verified against an untrusted or zero root",
        mechanism="The verifier accepts a proof against a root that was never properly committed (e.g. zero after init), so any leaf can be 'proven' present.",
        mitigation="Bind proofs to a finalized, validated root; reject zero/uninitialized roots.",
        tags=["zero root", "stale root", "inclusion proof"],
    ),
    dict(
        id="oak.merkle.second-preimage",
        bug_class="merkle-leaf-node-ambiguity",
        root_cause_category="proof-forgery",
        invariant_violated="proof-soundness",
        surfaces=[MERKLE],
        entrypoint_shape="merkle proof with no leaf/intermediate-node domain separation",
        title="Merkle second-preimage (leaf vs node ambiguity)",
        mechanism="Without domain separation between leaves and inner nodes, an intermediate node is presented as a leaf to forge an inclusion proof.",
        mitigation="Domain-separate leaf and node hashing (e.g. 0x00/0x01 prefixes).",
        tags=["second preimage", "domain separation"],
    ),
    dict(
        id="oak.bridge.message-replay",
        bug_class="cross-chain-message-replay",
        root_cause_category="replay",
        invariant_violated="replay-resistance",
        surfaces=[BRIDGE],
        entrypoint_shape="inbound message handler with no consumed-nonce / dedup set",
        title="Inbound bridge message replayable",
        mechanism="The handler does not record consumed message ids, so a delivered message can be replayed to repeat its effect (double mint/withdraw).",
        mitigation="Track and reject already-consumed message ids/nonces.",
        tags=["double spend", "nonce", "consumed"],
    ),
    dict(
        id="oak.bridge.source-unverified",
        bug_class="inbound-source-not-verified",
        root_cause_category="cross-domain-auth",
        invariant_violated="message-boundary-integrity",
        surfaces=[BRIDGE, XDOMAIN],
        entrypoint_shape="message handler that does not verify origin chain id / sender / endpoint",
        title="Inbound handler trusts unverified source",
        mechanism="The handler acts on a message without checking it came from the trusted remote/endpoint and source chain, letting a spoofed message drive privileged effects.",
        mitigation="Verify msg origin (endpoint, srcChainId, trusted remote / peer) before acting.",
        tags=["trusted remote", "peer", "endpoint", "srcChainId"],
    ),
    dict(
        id="oak.xdomain.sender-spoof",
        bug_class="cross-domain-sender-spoof",
        root_cause_category="cross-domain-auth",
        invariant_violated="access-control-consistency",
        surfaces=[XDOMAIN],
        entrypoint_shape="auth based on xDomainMessageSender / l1Sender without validating the messenger",
        title="Cross-domain sender spoofing",
        mechanism="Authorization relies on a cross-domain sender value that the attacker can influence (wrong messenger, missing messenger check), impersonating the privileged L1/L2 caller.",
        mitigation="Check msg.sender == trusted messenger AND xDomainMessageSender == expected.",
        tags=["xDomainMessageSender", "messenger"],
    ),
    dict(
        id="oak.slashing.equivocation-miss",
        bug_class="slashing-state-desync",
        root_cause_category="state-machine",
        invariant_violated="finality-integrity",
        surfaces=[SLASH],
        entrypoint_shape="slashing/operator-set transition that can desync stake vs registered set",
        title="Slashing/AVS operator-set desynchronization",
        mechanism="A transition (register/deregister/withdraw/checkpoint) updates one of stake or operator set but not the other, letting an operator avoid slashing or double-count stake.",
        mitigation="Atomic, checkpointed transitions; reconcile stake and operator set.",
        tags=["operator set", "checkpoint", "withdrawal queue"],
    ),
    dict(
        id="oak.zk.unbound-public-inputs",
        bug_class="zk-public-inputs-unbound",
        root_cause_category="proof-forgery",
        invariant_violated="proof-soundness",
        surfaces=[SIG, MERKLE],
        entrypoint_shape="zk verifier whose public inputs are not bound to the action's parameters",
        title="ZK proof accepted with unbound public inputs",
        mechanism="The verifier checks a proof but the public inputs are not tied to the on-chain effect (recipient/amount/nullifier), so a valid proof authorizes an unintended action or is replayed.",
        mitigation="Bind all effect parameters and a nullifier into the public inputs.",
        tags=["public inputs", "nullifier", "groth16", "plonk"],
    ),
]


# ---------------------------------------------------------------------------
# Worked examples — real settled findings (contest) and public incidents.
# ---------------------------------------------------------------------------
FINDINGS = [
    dict(
        id="c4.2024-01-decent.M-03",
        source="contest_finding",
        bug_class="alt-entrypoint-auth-bypass",
        root_cause_category="access-control",
        invariant_violated="access-control-consistency",
        surfaces=[BRIDGE, XDOMAIN, SIG],
        entrypoint_shape="public receiveFromBridge calls internal _swapAndExecute, skipping the retrieveAndCollectFees modifier",
        title="UTB.receiveFromBridge bypasses fee/signature verification",
        mechanism="receiveFromBridge is public with no access control and calls _swapAndExecute directly, skipping retrieveAndCollectFees (which validates the fee/swap-instruction signature via UTBFeeCollector.collectFees). An attacker executes a swap+payload with no signature and no fee.",
        mitigation="Restrict receiveFromBridge to the bridge adapter; or route it through the same verification.",
        provenance="Code4rena 2024-01-decent M-03 (issue #590)",
        tags=["UTB", "receiveFromBridge", "fee bypass", "unsigned"],
    ),
    dict(
        id="c4.2024-01-decent.H-01",
        source="contest_finding",
        bug_class="missing-auth-on-privileged-entrypoint",
        root_cause_category="access-control",
        invariant_violated="access-control-consistency",
        surfaces=[XDOMAIN, BRIDGE],
        entrypoint_shape="external setRouter with no owner check",
        title="DcntEth router address settable by anyone",
        mechanism="An access-control gap lets any caller set the trusted router on the DcntEth token, redirecting bridge mint/burn authority.",
        mitigation="Gate setRouter to owner; set once / immutable.",
        provenance="Code4rena 2024-01-decent H-01 (issue #721)",
        tags=["DcntEth", "setRouter", "config"],
    ),
    dict(
        id="c4.2024-01-decent.H-03",
        source="contest_finding",
        bug_class="failed-call-fund-misroute",
        root_cause_category="fund-routing",
        invariant_violated="solvency",
        surfaces=[BRIDGE],
        entrypoint_shape="executor that on failure forwards funds to an attacker-influenced address",
        title="DecentBridgeExecutor sends funds to a wrong address on failure",
        mechanism="When the destination execute() fails, funds are refunded to an address derived incorrectly, letting value be routed away from the intended recipient.",
        mitigation="Refund to the verified original sender; handle failure deterministically.",
        provenance="Code4rena 2024-01-decent H-03 (issue #436)",
        tags=["executor", "refund", "failure path"],
    ),
    dict(
        id="incident.nomad.2022",
        source="public_incident",
        bug_class="proof-verified-against-bad-root",
        root_cause_category="proof-forgery",
        invariant_violated="proof-soundness",
        surfaces=[MERKLE, BRIDGE],
        entrypoint_shape="process() accepts a message whose proof validates against an uninitialized (zero) trusted root",
        title="Nomad bridge: messages accepted against a zero trusted root",
        mechanism="An initialization set the trusted root to zero; the Replica then treated any message whose proof path resolved to zero as proven, so anyone could forge inbound messages and drain the bridge.",
        mitigation="Never treat zero/uninitialized roots as valid; validate committed roots.",
        provenance="Nomad bridge exploit, Aug 2022 (~$190M)",
        tags=["replica", "process", "merkle", "zero root", "forged message"],
    ),
    dict(
        id="incident.wormhole.2022",
        source="public_incident",
        bug_class="signature-verification-bypass",
        root_cause_category="signature-verification",
        invariant_violated="signature-authenticity",
        surfaces=[SIG, BRIDGE],
        entrypoint_shape="guardian-signature verification trusting an attacker-supplied system account",
        title="Wormhole: guardian signature verification bypass",
        mechanism="verify_signatures relied on a sysvar account that was not properly checked, letting the attacker spoof guardian signature verification and mint wrapped tokens without a legitimately signed VAA.",
        mitigation="Validate all accounts used in signature verification; bind to the real sysvar.",
        provenance="Wormhole exploit, Feb 2022 (~$326M)",
        tags=["guardian", "VAA", "verify_signatures", "mint"],
    ),
    dict(
        id="incident.polynetwork.2021",
        source="public_incident",
        bug_class="cross-domain-privileged-call",
        root_cause_category="access-control",
        invariant_violated="access-control-consistency",
        surfaces=[XDOMAIN, BRIDGE],
        entrypoint_shape="cross-chain manager executes attacker-crafted calldata reaching a privileged keeper-rotation function",
        title="Poly Network: cross-chain manager used to rotate the trusted keeper",
        mechanism="The cross-chain message executor could be made to call a privileged function that changes the trusted keeper/owner public keys, after which the attacker authorized arbitrary withdrawals.",
        mitigation="Restrict which target functions cross-chain messages may invoke; gate keeper rotation.",
        provenance="Poly Network exploit, Aug 2021 (~$611M)",
        tags=["EthCrossChainManager", "putCurEpochConPubKeyBytes", "keeper"],
    ),
    # ---- Deliberate VOCABULARY DECOY ----
    # Mentions "bridge" and "fee" heavily (vocabulary overlap with the M-03
    # query) but the MECHANISM is rounding/accounting, not verification/auth.
    # A mechanism retriever must rank this BELOW same-mechanism hits.
    dict(
        id="decoy.bridge-fee-rounding",
        source="contest_finding",
        bug_class="integer-rounding-dust",
        root_cause_category="rounding",
        invariant_violated="accounting-conservation",
        surfaces=[],  # not a verification/auth surface
        entrypoint_shape="fee computed with integer division on each bridge transfer",
        title="Bridge fee rounding leaks dust over many transfers",
        mechanism="The bridge fee is computed via integer division so a sub-unit remainder is lost each transfer; over many bridge transfers the accumulated dust is unaccounted. No authorization or verification is involved.",
        mitigation="Round in protocol's favor / carry remainder; track dust.",
        provenance="(constructed vocabulary decoy)",
        tags=["bridge", "fee", "rounding", "dust", "division"],
    ),
]


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def main() -> None:
    oak_rows = []
    for e in OAK:
        e = dict(e)
        e.setdefault("source", "oak_taxonomy")
        e.setdefault("provenance", "OAK attack matrix (taxonomy) — onchainattack.org/matrix")
        e.setdefault("mitigation", "")
        e.setdefault("tags", [])
        oak_rows.append(e)
    _write(DATA / "oak_matrix.jsonl", oak_rows)

    finding_rows = []
    for e in FINDINGS:
        e = dict(e)
        e.setdefault("mitigation", "")
        e.setdefault("tags", [])
        finding_rows.append(e)
    _write(DATA / "findings_corpus.jsonl", finding_rows)

    print(f"wrote {len(oak_rows)} OAK + {len(finding_rows)} findings to {DATA}")


if __name__ == "__main__":
    main()
