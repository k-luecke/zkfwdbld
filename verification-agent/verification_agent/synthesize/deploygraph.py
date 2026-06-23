"""M4.5 deploy-graph synthesis — stand up a target's collaborator graph.

Earlier homework refuted the premise that the missing piece was "the deploy graph"
in the abstract. This module tests that claim against a true-positive structural
bug: how much of a working `_seed()` can be derived from the M0 model ALONE,
target-agnostically, with zero protocol knowledge hardcoded?

What is derivable (and this module does it):
  - the target's owner-gated wiring setters (`set*`/`register*(address)` behind an
    auth modifier), read straight from the model's entry points;
  - the collaborator each setter wants, by matching the setter token to an
    in-scope contract name (setExecutor -> *Executor); unmatched slots are flagged
    as interface-mock slots, not guessed;
  - the deploy + wiring statements (no-arg constructors -> `new X()`).

What is NOT derivable from the model (named, not papered over) — the "semantic
mile": constructor arguments that carry meaning, ownership-transfer semantics,
mock BEHAVIOUR (a swapper that returns the fee token), call-payload contents, and
— the core blocker — a valid SIGNATURE for the honest control. These need
protocol semantics or signature construction, and the synthesizer says so per item.

So this module's honest output is a deploy+wiring skeleton plus a precise autonomy
ledger. It does not pretend the skeleton is a finished `_seed`.

State label: IMPLEMENTED (deploy+wiring derivation + autonomy ledger).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Auth-ish modifiers that mark an owner-gated wiring setter.
_AUTH_HINT = re.compile(r"only|auth|owner|admin|gov", re.I)
# A wiring setter: set<X>/register<X> taking a single address.
_SETTER = re.compile(r"^(set|register)([A-Z]\w*)$")


@dataclass
class DeployStmt:
    var: str
    contract: str
    ctor: str           # rendered constructor call args (may be "")
    is_mock_slot: bool  # an interface slot with no in-scope concrete impl
    iface: str = ""     # the interface a mock slot must implement


@dataclass
class WireStmt:
    setter: str
    collaborator_var: str
    token: str


@dataclass
class DeployGraph:
    target: str
    deploys: list[DeployStmt] = field(default_factory=list)
    wiring: list[WireStmt] = field(default_factory=list)
    semantic_gaps: list[str] = field(default_factory=list)

    def render_state_decls(self) -> str:
        """State-variable declarations for the deployed contracts.

        A VerifyGate scenario calls the attack/control via `this.*`, so the
        deployed contracts must be STATE, not `_seed()` locals — otherwise they
        are invisible to the external hooks. The synthesizer emits the decls so
        the deploys can be plain assignments.
        """
        out = []
        for d in self.deploys:
            if d.is_mock_slot:
                continue
            out.append(f"    {d.contract} internal {d.var};")
        return "\n".join(out)

    def render_seed(self, as_assignment: bool = True) -> str:
        """Render the AUTONOMOUS deploy+wiring portion of a `_seed()` body.

        `as_assignment=True` assigns to pre-declared state vars (the form a gate
        scenario needs); `False` emits local declarations (standalone view).
        """
        lines = []
        for d in self.deploys:
            if d.is_mock_slot:
                lines.append(
                    f"        // MOCK SLOT: deploy a mock implementing {d.iface} "
                    f"(behaviour is a semantic gap)")
                lines.append(f"        // {d.var} = /* mock {d.iface} */;")
            elif as_assignment:
                lines.append(f"        {d.var} = new {d.contract}({d.ctor});")
            else:
                lines.append(f"        {d.contract} {d.var} = new {d.contract}({d.ctor});")
        for w in self.wiring:
            lines.append(f"        target_.{w.setter}(address({w.collaborator_var}));")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "deploys": [{"var": d.var, "contract": d.contract,
                         "mock_slot": d.is_mock_slot, "iface": d.iface}
                        for d in self.deploys],
            "wiring": [{"setter": w.setter, "collaborator": w.collaborator_var}
                       for w in self.wiring],
            "semantic_gaps": self.semantic_gaps,
        }


def _contracts(model: dict) -> list[str]:
    return [c.get("name", "") for c in model.get("contracts", [])]


def _concrete_contracts(model: dict) -> list[str]:
    """Names of contracts that can actually be `new`'d (not interfaces/abstract)."""
    out = []
    for c in model.get("contracts", []):
        if c.get("kind") in ("interface", "abstract"):
            continue
        n = c.get("name", "")
        # An interface conventionally named IFoo with no `kind` signal.
        if re.match(r"^I[A-Z]", n):
            continue
        out.append(n)
    return out


def _entry_points(model: dict, contract: str) -> list[dict]:
    return [e for e in model.get("entry_points", []) if e.get("contract") == contract]


def _is_wiring_setter(ep: dict) -> tuple[bool, str]:
    m = _SETTER.match(ep.get("name", ""))
    if not m:
        return False, ""
    sig = ep.get("signature", "")
    if "address" not in sig:
        return False, ""
    if not any(_AUTH_HINT.search(mod) for mod in ep.get("modifiers", [])):
        return False, ""
    return True, m.group(2)  # the token after set/register


def _match_collaborator(token: str, contracts: list[str], target: str) -> str | None:
    """Find an in-scope contract for a setter token (Executor -> *Executor*)."""
    tl = token.lower()
    cands = [c for c in contracts if c and c != target and tl in c.lower()]
    if not cands:
        return None
    # Prefer the most specific (longest) name match.
    return sorted(cands, key=len)[-1]


def _lower_first(s: str) -> str:
    return s[:1].lower() + s[1:] if s else s


class DeployGraphSynthesizer:
    """Derive a target's collaborator deploy+wiring from the M0 model alone."""

    def synthesize(self, model: dict, target: str) -> DeployGraph:
        contracts = _concrete_contracts(model)
        g = DeployGraph(target=target)
        g.deploys.append(DeployStmt(var="target_", contract=target, ctor="",
                                    is_mock_slot=False))
        seen = {target}
        for ep in _entry_points(model, target):
            ok, token = _is_wiring_setter(ep)
            if not ok:
                continue
            collab = _match_collaborator(token, contracts, target)
            var = _lower_first(token)
            if collab:
                if collab not in seen:
                    g.deploys.append(DeployStmt(var=var, contract=collab, ctor="",
                                                is_mock_slot=False))
                    seen.add(collab)
                g.wiring.append(WireStmt(setter=ep["name"], collaborator_var=var,
                                         token=token))
            else:
                iface = f"I{token}"
                g.deploys.append(DeployStmt(var=var, contract=iface, ctor="",
                                            is_mock_slot=True, iface=iface))
                g.wiring.append(WireStmt(setter=ep["name"], collaborator_var=var,
                                         token=token))

        # The semantic mile the model cannot supply — named per item.
        g.semantic_gaps = [
            "constructor ARGS with meaning (model carries no constructor params)",
            "ownership-transfer semantics (e.g. collaborator owned by the target)",
            "mock BEHAVIOUR for interface slots (e.g. a swapper that returns a token)",
            "honest-control CALL PAYLOADS (struct fields, sink selector)",
            "a VALID SIGNATURE for the honest control (the core blocker)",
        ]
        return g
