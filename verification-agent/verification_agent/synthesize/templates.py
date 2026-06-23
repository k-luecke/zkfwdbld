"""Target-AGNOSTIC Solidity templates for synthesized gate scenarios.

The whole point of M4.5 is that the machine writes the scenario. For that to mean
anything, the template must carry NO target-specific knowledge — no protocol
names, no hand-encoded deploy steps. It is filled only from the structural shape
of a Seer lead (the unguarded entrypoint, the guard it bypasses), so a scenario
that confirms cannot have been rigged by smuggling the answer into the template.

The template reproduces the *structural alt-entrypoint-auth-bypass mechanism*:
a privileged sink reached by a guarded entrypoint AND an unguarded sibling. It
generates two scenarios from every lead:

  faithful       — the honest invariant (every privileged effect was authorized);
                   the attack calls the unguarded sibling -> invariant breaks ->
                   the gate should CONFIRM.

  rigged-control — a deliberately too-brittle invariant (effectCount == 0) that
                   any honest use breaks. This is the M4.5 wrong-reason guard:
                   if the machine could synthesize a rigged predicate that slips
                   through, the gate's Control phase MUST reject it. We generate
                   it on purpose and assert the rejection, so the anti-hallucination
                   property of machine-written scenarios is proven, not hoped for.

NOTE ON SCOPE: a self-contained scenario proves the synthesis PIPELINE and the
Control guarantee. It does NOT certify a real finding — only execution against
the real deployed code can do that (the unguarded sibling must actually exist and
actually reach the sink without authorization). That boundary lives in
synthesizer.py, not here.

State label: IMPLEMENTED.
"""

from __future__ import annotations

import re

_HEADER = """// SPDX-License-Identifier: UNLICENSED
// MACHINE-SYNTHESIZED by Verification-Agent M4.5 from a Seer structural lead.
// Target-agnostic structural reproduction of: {entrypoint} bypassing {guard}.
pragma solidity ^0.8.0;

import {{VerifyGate}} from "./VerifyGate.sol";

// Generated privileged sink: the effect an attacker wants executed. In honest
// operation it is reached only through the guarded path.
contract SynthSink_{tag} {{
    uint256 public effectCount;
    function privilegedEffect() external {{ effectCount++; }}
}}

// Generated target reproducing the alt-entrypoint shape the lead describes:
//   - guardedSibling(): the protected path (modifier asserts authorization)
//   - {entrypoint}(): the UNGUARDED sibling the lead flagged, reaching the same
//     sink with no authorization check.
contract SynthTarget_{tag} {{
    SynthSink_{tag} public sink;
    mapping(address => bool) public authorized;
    uint256 public authorizedEffects; // increments ONLY on the guarded path
    address public admin;

    constructor(SynthSink_{tag} s) {{ sink = s; admin = msg.sender; }}
    function setAuthorized(address a, bool ok) external {{
        require(msg.sender == admin, "only admin");
        authorized[a] = ok;
    }}
    modifier {guardmod}() {{ require(authorized[msg.sender], "not authorized"); _; }}

    // The guarded entrypoint (the sibling the lead's unguarded path bypasses).
    function guardedSibling() external {guardmod} {{
        authorizedEffects++;
        sink.privilegedEffect();
    }}

    // The unguarded entrypoint named by the lead: reaches the sink, no modifier.
    function {entrypoint}() external {{
        sink.privilegedEffect();
    }}
}}

// Shared seed + independent invariant + honest control. The two cases below
// differ ONLY in the invariant (faithful vs rigged) — the attack is identical.
abstract contract SynthScenario_{tag} is VerifyGate {{
    SynthSink_{tag} internal sink;
    SynthTarget_{tag} internal target;
    address internal honest;
    address internal attacker;

    function _seed() internal override {{
        honest = makeAddr("honest");
        attacker = makeAddr("attacker");
        sink = new SynthSink_{tag}();
        target = new SynthTarget_{tag}(sink);
        target.setAuthorized(honest, true); // the honest actor is authorized
    }}

    // Independent of the attack: every privileged effect must have been authorized.
    function _invariantHolds() public view virtual override returns (bool) {{
        return sink.effectCount() == target.authorizedEffects();
    }}

    // Control: a legitimate, authorized use of the guarded path. Preserves the
    // invariant (both counters advance together).
    function honestAction() external override {{
        vm.prank(honest);
        target.guardedSibling();
    }}

    function describeInvariant() public pure virtual override returns (string memory) {{
        return "every privileged effect is authorized: sink.effectCount == target.authorizedEffects";
    }}

    // The attack: call the unguarded sibling. A privileged effect with no
    // authorization -> effectCount advances while authorizedEffects does not.
    function runAttack() external override {{
        vm.prank(attacker);
        target.{entrypoint}();
    }}
}}

// FAITHFUL: honest invariant; the unguarded call should break it -> CONFIRMED.
contract {faithful} is SynthScenario_{tag} {{
    function caseId() public pure override returns (string memory) {{
        return "{entrypoint}_alt_entrypoint_bypass__SYNTH_FAITHFUL";
    }}
}}

// RIGGED-CONTROL: a too-brittle invariant (effectCount == 0) any honest use
// breaks. The machine "could" synthesize this to force a break — the gate's
// Control phase MUST reject it first. Expected: REJECTED_MALFORMED_CONTROL.
contract {rigged} is SynthScenario_{tag} {{
    function caseId() public pure override returns (string memory) {{
        return "{entrypoint}__SYNTH_RIGGED_predicate";
    }}
    function describeInvariant() public pure override returns (string memory) {{
        return "RIGGED PREDICATE (demo): sink.effectCount == 0 (any honest use breaks it)";
    }}
    function _invariantHolds() public view override returns (bool) {{
        return sink.effectCount() == 0;
    }}
}}
"""


def _ident(name: str) -> str:
    """Reduce a lead name to a safe Solidity identifier."""
    s = re.sub(r"[^0-9a-zA-Z_]", "_", name or "").strip("_")
    if not s or not re.match(r"[a-zA-Z_]", s[0]):
        s = "fn_" + s
    return s


def build_structural_sources(entrypoint: str, guard: str) -> tuple[str, str, str]:
    """Return (solidity_source, faithful_contract, rigged_contract) for a lead.

    Filled only from the lead's structural shape; carries no target specifics.
    """
    ep = _ident(entrypoint)
    # The bypassed guard becomes a *generic* modifier name (label only); if it
    # collides with the entrypoint, suffix it so the contract still compiles.
    guardmod = _ident(guard) or "onlyAuthorized"
    if guardmod == ep:
        guardmod = guardmod + "_mod"
    tag = ep
    faithful = f"Synth_{tag}_Faithful"
    rigged = f"Synth_{tag}_Rigged"
    src = _HEADER.format(
        entrypoint=ep, guard=guard or "(auth modifier)", guardmod=guardmod,
        tag=tag, faithful=faithful, rigged=rigged,
    )
    return src, faithful, rigged
