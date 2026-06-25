"""Protocol-rule extraction (Move 2) — hunt stated-rule violations, not shapes.

M3 was loud because it reasoned from STRUCTURE alone: "this function is unguarded
-> a lead." That can't tell a real violation from a legitimately permissionless
function, which is why design-permissionless functions all surfaced as noise.

This module makes a hypothesis target a violation of the PROTOCOL'S OWN STATED
RULE. The protocol states a rule whenever its code gates an effect: a guarded
sibling G reaches an effect E while carrying a modifier M (auth, OR a fee/precondition
gate). That is the claim "reaching E requires M". A claimed-rule VIOLATION is an
entrypoint F that reaches the SAME effect E WITHOUT M. That is a real lead — "the protocol claims only-via-M causes E; here is a
path where not-M causes E" — as opposed to "F is unguarded", which is noise.

Rules are PRIORS, not truth (constraint #3): a stated rule (modifier asymmetry or a
NatSpec authority phrase) is "worth testing whether this holds", never an established
fact. The gate still adjudicates; this only sharpens what gets proposed.

The extraction is target-agnostic — it reads the call graph + modifiers (and,
optionally, NatSpec authority phrases from source). No protocol literal appears here.

State label: IMPLEMENTED (modifier/role asymmetry) / NatSpec scan = corroborating.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..model.surface import is_auth_modifier

# A meaningful protected effect is an INTERNAL, state-changing function. Two
# exclusions weed out the structural noise that paired guarded+unguarded siblings
# over trivia (require()/_msgSender()/getters/builtins):
#   (a) anything that is an external/builtin/high-level-call representation, and
#   (b) control-flow + pure/view helpers (getters, calculators, converters).
# Exact-word noise (matched whole):
_NOISE_EXACT = {
    "require(bool,string)", "require(bool)", "require", "assert", "revert",
    "_msgSender", "_msgData", "_successCheck", "balanceOf", "totalSupply",
    "allowance", "decimals", "symbol", "name", "owner", "wards", "_toUint128",
}
# Prefix/substring noise (view/pure/getter shapes), matched anywhere it applies:
_NOISE_NAME = re.compile(
    r"^(get|is|has)[A-Z_]|calculate|preview|price|decimals|"
    r"^_to[A-Z]|^_calculate|^_get|^_is|^_has|"
    # type-conversion helpers (addressToBytes32, bytes32ToAddress, toUint128) —
    # pure serialization, never a protected state effect. Keyed on a type->type
    # shape so real effects like _sendToRecipient are NOT excluded.
    r"(address|bytes32|bytes|uint\d*|int\d*|string|bool)to"
    r"(address|bytes32|bytes|uint|int|string|bool)", re.I)

# NatSpec authority phrases that assert a stated rule in prose.
_NATSPEC_AUTHORITY = re.compile(
    r"\bonly\b.*\b(can|may|able|allowed|callable)\b|"
    r"\b(can|may|must)\s+only\b|"
    r"\bcallable only\b|\bonly callable\b|"
    r"\bmust be (called|invoked) by\b|"
    r"\bonly the\b", re.I)


@dataclass
class ClaimedRule:
    """A rule the protocol states over an effect: 'reaching E requires M'."""
    effect: str
    required_modifier: str
    guarded_by: list[str]            # sibling entrypoints that enforce M before E
    source: str = "modifier-asymmetry"   # or "natspec"
    natspec: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"effect": self.effect, "required_modifier": self.required_modifier,
                "guarded_by": self.guarded_by, "source": self.source,
                "natspec": self.natspec}


@dataclass
class RuleViolation:
    """An entrypoint that reaches a stated-rule-protected effect without the guard."""
    contract: str
    function: str
    effect: str
    required_modifier: str
    guarded_siblings: list[str] = field(default_factory=list)
    natspec: str = ""

    @property
    def key(self) -> str:
        return f"{self.contract}.{self.function}"

    def statement(self) -> str:
        cite = f" (NatSpec: \"{self.natspec.strip()[:80]}\")" if self.natspec else ""
        g = self.guarded_siblings[0] if self.guarded_siblings else "a guarded sibling"
        return (f"The protocol enforces `{self.required_modifier}` before `{self.effect}` "
                f"(on `{g}`){cite}; `{self.key}` reaches `{self.effect}` without it — "
                f"testing whether 'only via {self.required_modifier} causes {self.effect}' holds.")

    def to_dict(self) -> dict[str, Any]:
        return {"target": self.key, "effect": self.effect,
                "required_modifier": self.required_modifier,
                "guarded_siblings": self.guarded_siblings,
                "natspec": self.natspec, "statement": self.statement()}


def _adjacency(model: dict) -> tuple[dict[str, set[str]], set[str]]:
    """Adjacency plus the set of in-scope INTERNAL nodes (callers, and callees of
    internal edges). The internal set lets us treat a qualified internal function
    (Contract.fn) as a meaningful effect while still excluding external high-level
    calls (Token.transfer), which a bare-string '.' check could not distinguish."""
    adj: dict[str, set[str]] = defaultdict(set)
    internal: set[str] = set()
    for e in model.get("call_graph", []):
        caller = e.get("caller", "")
        callee = e.get("callee", "")
        adj[caller].add(callee)
        if caller:
            internal.add(caller)
        if callee and not e.get("external", False):
            internal.add(callee)
    return adj, internal


def _reach(adj: dict[str, set[str]], start: str, depth: int = 5) -> set[str]:
    seen: set[str] = set()
    frontier = {start}
    for _ in range(depth):
        nxt: set[str] = set()
        for n in frontier:
            for c in adj.get(n, ()):
                if c not in seen:
                    seen.add(c)
                    nxt.add(c)
        if not nxt:
            break
        frontier = nxt
    return seen


def _is_meaningful_effect(callee: str, modifiers: set[str],
                          internal_nodes: frozenset[str] | set[str] = frozenset()) -> bool:
    if not callee or callee in modifiers:
        return False
    if "(" in callee or "HIGH_LEVEL_CALL" in callee:
        return False
    if "." in callee:
        # Qualified: a real in-scope internal function IS a meaningful effect
        # (multi-hop flows resolve to Contract.fn); an external high-level call
        # (not in the internal set) is not the internal state effect we test.
        if callee not in internal_nodes:
            return False
        bare = callee.rsplit(".", 1)[-1]
    else:
        bare = callee
    if bare in _NOISE_EXACT or _NOISE_NAME.search(bare):
        return False
    return True


def _natspec_for(ep: dict, source_root: Path | None) -> str:
    """Read the comment block immediately above the function, if source is available."""
    if not source_root:
        return ""
    sf = ep.get("source_file")
    line = ep.get("source_line")
    if not sf or not line:
        return ""
    p = source_root / sf
    if not p.exists():
        return ""
    try:
        lines = p.read_text().splitlines()
    except Exception:
        return ""
    # Walk upward from the declaration collecting a contiguous comment block.
    buf = []
    i = min(line - 2, len(lines) - 1)  # 0-indexed line just above the declaration
    while i >= 0:
        s = lines[i].strip()
        if s.startswith(("///", "*", "/**", "//", "*/")):
            buf.append(s.lstrip("/*  ").rstrip("*/ "))
            i -= 1
        elif s == "":
            i -= 1
        else:
            break
    return " ".join(reversed(buf)).strip()


def extract_rules_and_violations(
    model: dict, source_root: str | None = None,
) -> tuple[list[ClaimedRule], list[RuleViolation]]:
    """Derive stated rules (modifier asymmetry, + NatSpec) and their violations."""
    adj, internal_nodes = _adjacency(model)
    eps = [e for e in model.get("entry_points", []) if e.get("is_entry_point")]
    all_mods = {m for e in eps for m in (e.get("modifiers") or [])}
    src = Path(source_root) if source_root else None

    # Reachability + guard set per entrypoint.
    info = {}
    for e in eps:
        key = f"{e['contract']}.{e['name']}"
        info[key] = {
            "ep": e,
            "mods": set(e.get("modifiers") or []),
            "reach": _reach(adj, key),
        }

    # For each meaningful effect E, who reaches it and with which guarding modifier.
    guarded: dict[str, list[tuple[str, str]]] = defaultdict(list)   # E -> [(G, M)]
    reachers: dict[str, list[str]] = defaultdict(list)              # E -> [F]
    for key, d in info.items():
        for callee in d["reach"]:
            if not _is_meaningful_effect(callee, all_mods, internal_nodes):
                continue
            reachers[callee].append(key)
            for m in d["mods"]:
                guarded[callee].append((key, m))

    rules: list[ClaimedRule] = []
    violations: list[RuleViolation] = []
    seen_rule = set()
    seen_v = set()
    for effect, gpairs in guarded.items():
        guard_mods = {m for _, m in gpairs}
        guard_fns = sorted({g for g, _ in gpairs})
        for m in guard_mods:
            rk = (effect, m)
            if rk not in seen_rule:
                seen_rule.add(rk)
                rules.append(ClaimedRule(effect=effect, required_modifier=m,
                                         guarded_by=[g for g, mm in gpairs if mm == m]))
            # A violation: an entrypoint F reaching E that does NOT carry M.
            for f in reachers[effect]:
                if m in info[f]["mods"]:
                    continue          # F enforces the rule -> not a violation
                if f in [g for g, mm in gpairs if mm == m]:
                    continue          # F is the guarded sibling itself
                ep = info[f]["ep"]
                vk = (f, effect, m)
                if vk in seen_v:
                    continue
                seen_v.add(vk)
                violations.append(RuleViolation(
                    contract=ep["contract"], function=ep["name"],
                    effect=effect, required_modifier=m,
                    guarded_siblings=[g for g, mm in gpairs if mm == m],
                    natspec=_natspec_for(ep, src),
                ))
    return rules, violations


def natspec_only_claims(model: dict, source_root: str) -> list[str]:
    """PROBE: entrypoints whose NatSpec asserts authority but carry NO modifier.

    These are rules stated only in prose (not in code). Reported separately so we
    can measure whether NatSpec adds signal beyond modifier asymmetry, without
    letting it inflate the lead count in the core path.
    """
    src = Path(source_root)
    out = []
    for e in model.get("entry_points", []):
        if e.get("modifiers"):
            continue
        ns = _natspec_for(e, src)
        if ns and _NATSPEC_AUTHORITY.search(ns):
            out.append(f"{e['contract']}.{e['name']}: \"{ns.strip()[:90]}\"")
    return out
