"""Build KB queries from M0 output.

The honest, M0-derivable signal for a function is its surface tags + its
name/signature/evidence. Mechanism hints (root_cause/invariant) are optional and
get filled in by M3 as it forms a hypothesis — not assumed here.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from typing import Any

from .schema import KBQuery


def query_from_surface_function(fn: dict[str, Any]) -> KBQuery:
    """Build a query from an M0 verification-surface entry (a FunctionInfo dict).

    Uses only what M0 actually produces: the surface tags and the function's
    name/signature/evidence. No mechanism hint is invented.
    """
    surfaces = list(fn.get("surfaces", []))
    evidence_terms: list[str] = []
    for terms in (fn.get("surface_evidence") or {}).values():
        evidence_terms.extend(t.replace("(body)", "") for t in terms)
    text = " ".join(filter(None, [
        fn.get("name", ""),
        fn.get("signature", ""),
        " ".join(fn.get("modifiers", []) or []),
        " ".join(evidence_terms),
    ]))
    return KBQuery(surfaces=surfaces, text=text)


def query_for_m03_surface() -> KBQuery:
    """The M-03 surface as a query (for the M2 demo).

    Represents the UTB fee/auth entrypoint cluster: a privileged swap-execute
    reachable on the bridge-inbound / cross-domain / signature surface. We pass
    only surfaces + free text (the M0-derivable signal); the mechanism hint is
    added in a second demo query to show mechanism-keyed narrowing.
    """
    return KBQuery(
        surfaces=["bridge_inbound_handler", "cross_domain_auth",
                  "signature_proof_verification"],
        text=("receiveFromBridge swapAndExecute fee collector signature "
              "privileged execute reachable without modifier"),
    )
