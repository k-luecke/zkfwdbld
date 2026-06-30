"""Multi-hop reachability: the call-graph fix (review finding #1).

Before the fix, the model emitted call edges only for entry points and left
internal callees unqualified, so both Seer and the protocol-rule extractor could
only see DIRECT entrypoint->callee edges. A privileged sink reachable only through
an internal chain (ext -> A -> B -> sink) was invisible.

This model has the guarded and the unguarded entrypoint reach the SAME deep sink
through DIFFERENT intermediate functions, so the bypass is detectable ONLY with
transitive, qualified traversal — a direct-edge reading finds no shared sink.
No network/forge/slither.
"""

from types import SimpleNamespace

from verification_agent.hypothesize.protocol_rules import extract_rules_and_violations
from verification_agent.pathfind import SeerStructuralBackend
from verification_agent.pathfind.schema import PathStatus


def _multihop_model() -> dict:
    # A.extGuarded (onlyOwner) -> A.guardPath -> A.privilegedSink
    # A.extOpen    (no guard)  -> A.openPath  -> A.privilegedSink
    # Shared sink is two hops away via distinct intermediates: no shared DIRECT
    # callee, so only transitive reachability finds the bypass.
    return {
        "entry_points": [
            {"contract": "A", "name": "extGuarded", "is_entry_point": True,
             "modifiers": ["onlyOwner"]},
            {"contract": "A", "name": "extOpen", "is_entry_point": True,
             "modifiers": []},
        ],
        "call_graph": [
            {"caller": "A.extGuarded", "callee": "A.guardPath", "external": False},
            {"caller": "A.guardPath", "callee": "A.privilegedSink", "external": False},
            {"caller": "A.extOpen", "callee": "A.openPath", "external": False},
            {"caller": "A.openPath", "callee": "A.privilegedSink", "external": False},
        ],
    }


def test_seer_finds_multihop_bypass():
    model = _multihop_model()
    hyp = SimpleNamespace(id="H-mh", target_contract="A",
                          target_function="extGuarded", root_cause="access-control")
    r = SeerStructuralBackend().find_path(hyp, model)
    assert r.status is PathStatus.FOUND
    # The deep sink is reached by the guarded entry AND the unguarded extOpen,
    # two hops down each chain — only transitive traversal surfaces this.
    assert r.attack_entrypoint == "extOpen"
    assert "A.privilegedSink" in r.reaches
    assert r.guard_bypassed == "onlyOwner"


def test_protocol_rules_finds_multihop_violation():
    rules, violations = extract_rules_and_violations(_multihop_model())
    # A stated rule: reaching A.privilegedSink requires onlyOwner (the guarded path
    # carries it). The unguarded extOpen reaches the same deep sink without it.
    assert any(r.effect == "A.privilegedSink" and r.required_modifier == "onlyOwner"
               for r in rules), [r.statement() for r in rules]
    assert any(v.function == "extOpen" and v.effect == "A.privilegedSink"
               for v in violations), [(v.function, v.effect) for v in violations]


def test_function_edges_qualifies_internal_and_includes_low_level():
    # Emission side of the fix: internal callees qualified to Contract.fn, builtins
    # left bare, high-level calls external+qualified, low-level calls present as edges.
    from verification_agent.model.slither_runner import _function_edges

    def fn(name, contract=None):
        return SimpleNamespace(
            name=name,
            contract_declarer=SimpleNamespace(name=contract) if contract else None)

    func = SimpleNamespace(
        name="entry",
        internal_calls=[SimpleNamespace(function=fn("_helper", "A")),
                        SimpleNamespace(function=fn("require"))],   # builtin: no declarer
        high_level_calls=[(SimpleNamespace(name="Token"), SimpleNamespace(name="transfer"))],
        low_level_calls=[SimpleNamespace(name="delegatecall")],
    )
    pairs = {(e.caller, e.callee, e.external) for e in _function_edges(func, "A")}
    assert ("A.entry", "A._helper", False) in pairs      # internal -> qualified node
    assert ("A.entry", "require", False) in pairs         # builtin stays bare (noise)
    assert ("A.entry", "Token.transfer", True) in pairs   # high-level: external, qualified
    assert ("A.entry", "delegatecall", True) in pairs     # low-level edge now emitted


def test_direct_only_model_still_works():
    # A 1-hop (direct) bypass must still be found — transitive must not regress the
    # base case the saved Decent model relies on.
    model = {
        "entry_points": [
            {"contract": "B", "name": "guarded", "is_entry_point": True,
             "modifiers": ["auth"]},
            {"contract": "B", "name": "open", "is_entry_point": True, "modifiers": []},
        ],
        "call_graph": [
            {"caller": "B.guarded", "callee": "_doEffect", "external": False},
            {"caller": "B.open", "callee": "_doEffect", "external": False},
        ],
    }
    hyp = SimpleNamespace(id="H-d", target_contract="B",
                          target_function="open", root_cause="access-control")
    r = SeerStructuralBackend().find_path(hyp, model)
    assert r.status is PathStatus.FOUND
    assert r.attack_entrypoint == "open" and "_doEffect" in r.reaches
