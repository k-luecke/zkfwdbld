"""Invariant pattern library — turns a mechanism into a measuring stick.

This is where M3 earns its keep. Given a KB-grounded mechanism (bug_class /
root_cause / invariant_violated), produce a mechanism-specific `InvariantSpec`
with explicit baseline / control / break expectations — one that will survive
the gate's Baseline and Control phases rather than producing a
MALFORMED_CONTROL rejection.

The patterns are drawn from the brief's invariant library: solvency, supply
conservation, monotonicity, access-control consistency, replay-resistance,
finality / message-boundary integrity.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from .schema import InvariantSpec

# Map a root-cause category to a predicate template. Keyed by root_cause first,
# then bug_class for finer cases.
_BY_ROOT_CAUSE = {
    "access-control": dict(
        name="authorization-conservation",
        predicate_kind="counting-conservation",
        description=(
            "Every execution of the privileged effect was authorized through the "
            "canonical gate: count(privileged-effect) == count(authorized-invocations)."),
        baseline_expectation="0 effects, 0 authorizations -> equal.",
        control_expectation="one honest, authorized call: +1 effect, +1 authorization -> equal.",
        break_expectation="attacker triggers the effect without authorization: effects > authorizations.",
        measured_quantity="count of privileged effect vs count of authorized (paid/signed) invocations",
    ),
    "cross-domain-auth": dict(
        name="caller-authenticity",
        predicate_kind="counting-conservation",
        description=(
            "The privileged effect only occurs when the verified cross-domain "
            "caller is the trusted source: effects == effects-from-trusted-caller."),
        baseline_expectation="no effects -> equal.",
        control_expectation="a message from the trusted remote: +1 effect, +1 trusted -> equal.",
        break_expectation="a spoofed/unverified caller triggers the effect: effects > trusted.",
        measured_quantity="privileged effects vs effects attributable to the trusted caller",
    ),
    "replay": dict(
        name="replay-resistance",
        predicate_kind="one-time-use",
        description=(
            "Each authorization (signature / message / nonce) authorizes at most "
            "one effect: consumed-authorizations are never re-accepted."),
        baseline_expectation="no authorization consumed twice on honest use.",
        control_expectation="a fresh authorization is consumed exactly once.",
        break_expectation="a previously-consumed authorization is accepted again.",
        measured_quantity="per-authorization consumption count (must stay <= 1)",
    ),
    "signature-verification": dict(
        name="signature-authenticity",
        predicate_kind="binding-integrity",
        description=(
            "A privileged effect occurs only under a signature by the trusted "
            "signer over exactly the parameters that drive the effect."),
        baseline_expectation="no effect without a signer-bound signature.",
        control_expectation="a correctly signed call produces the effect.",
        break_expectation="an effect occurs under a forged/zero/unbound signature.",
        measured_quantity="effects vs effects backed by a valid signer-bound signature",
    ),
    "proof-forgery": dict(
        name="proof-soundness",
        predicate_kind="binding-integrity",
        description=(
            "An inclusion/zk proof is accepted only against a finalized, trusted "
            "root with all effect parameters bound to the public inputs."),
        baseline_expectation="no acceptance against a zero/untrusted root.",
        control_expectation="a valid proof against the finalized root is accepted.",
        break_expectation="a forged proof (bad root / unbound inputs) is accepted.",
        measured_quantity="accepted proofs vs proofs valid against the finalized root",
    ),
    "fund-routing": dict(
        name="solvency-conservation",
        predicate_kind="value-conservation",
        description=(
            "Value out of the protocol equals value legitimately owed: no path "
            "routes funds to an attacker-influenced recipient."),
        baseline_expectation="inflow == outflow + holdings on honest use.",
        control_expectation="an honest withdrawal conserves the balance sheet.",
        break_expectation="a path sends value to an unintended recipient (deficit).",
        measured_quantity="protocol balance sheet (inflow vs outflow + holdings)",
    ),
    "rounding": dict(
        name="accounting-conservation",
        predicate_kind="value-conservation",
        description="Aggregate accounting is conserved across operations (no dust leak).",
        baseline_expectation="sum of parts == whole at rest.",
        control_expectation="an honest operation conserves the aggregate.",
        break_expectation="repeated operations leak an unaccounted remainder.",
        measured_quantity="aggregate accounting identity",
    ),
    "state-machine": dict(
        name="stake-set-consistency",
        predicate_kind="counting-conservation",
        description=(
            "Slashable stake and the registered operator set stay reconciled "
            "across every transition."),
        baseline_expectation="stake and operator set agree at rest.",
        control_expectation="a normal register/withdraw keeps them reconciled.",
        break_expectation="a transition desyncs stake from the operator set.",
        measured_quantity="reconciliation of stake vs registered operator set",
    ),
}

# A weak, generic fallback for functions with no strong mechanism match. Its
# vagueness is the point: a vague predicate is *meant* to fare poorly, and the
# gate's MALFORMED guards exist precisely to catch it if M3 over-reaches.
_GENERIC = dict(
    name="state-integrity",
    predicate_kind="generic",
    description="No reachable state violates the protocol's intended accounting/auth invariants.",
    baseline_expectation="holds on honest seeded state.",
    control_expectation="an honest action preserves it.",
    break_expectation="(unspecified) — weak predicate; likely MALFORMED at the gate.",
    measured_quantity="(unspecified)",
)

# Known runnable gate bindings: a hypothesis whose mechanism + target matches one
# of these can be handed straight to the existing M1 VerifyGate case. Data only.
_GATE_BINDINGS = {
    ("UTB", "receiveFromBridge"): "DecentReceiveFromBridgeBypass",
}


def invariant_for(
    *,
    root_cause: str,
    bug_class: str,
    invariant_violated: str,
    target_contract: str = "",
    target_function: str = "",
) -> InvariantSpec:
    template = _BY_ROOT_CAUSE.get(root_cause)
    if template is None:
        template = _GENERIC
    binding = _GATE_BINDINGS.get((target_contract, target_function))
    spec = InvariantSpec(**template, gate_binding=binding)
    # Prefer the prior's named invariant when it is more specific than the
    # template's generic name (keeps provenance from the KB visible).
    if invariant_violated and invariant_violated not in spec.name:
        spec.description = f"[{invariant_violated}] " + spec.description
    return spec
