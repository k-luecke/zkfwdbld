"""Seer — structural reachability backend.

This is the agent's structural-reachability reasoning core (not an LLM scanner).
It searches the M0 call graph TOWARD the break predicate: for access-control /
reachability mechanisms, the break is "a privileged effect is reached without
the authorization the protocol enforces elsewhere". Seer finds that by locating
a privileged sink reached by BOTH a guarded entrypoint and an UNGUARDED one —
the unguarded entrypoint is the concrete bypass path.

On the Decent model this independently rediscovers M-03: `_swapAndExecute` is
reached by the guarded `swapAndExecute` (modifier `retrieveAndCollectFees`) AND
by the unguarded `receiveFromBridge` — so Seer reports `receiveFromBridge` as the
attack path bypassing `retrieveAndCollectFees`, without being told. That is the
"reproduce a known path before discovering novel ones" acceptance test.

State label: IMPLEMENTED.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from .schema import PathResult, PathStatus

# Mechanisms this structural backend reasons about (reachability / auth).
_IN_SCOPE = {"access-control", "cross-domain-auth"}

# Callee names that are not privileged sinks (modifiers, encoders, low-level).
_CALLEE_NOISE = {
    "abi.encode()", "abi.encodePacked()", "abi.decode()", "call", "delegatecall",
    "staticcall", "require", "assert", "low_level_call",
}

# Known runnable gate cases for discovered paths (data only — not an import).
_GATE_BINDINGS = {
    ("UTB", "receiveFromBridge"): "DecentReceiveFromBridgeBypass",
}


class SeerStructuralBackend:
    name = "seer-structural"

    def available(self) -> bool:
        return True  # pure structural reasoning over the M0 model; always usable

    def find_path(self, hypothesis: Any, model: dict[str, Any],
                  repo_dir: Any | None = None, timeout: int = 120) -> PathResult:
        t0 = time.time()
        hid = getattr(hypothesis, "id", "?")
        contract = getattr(hypothesis, "target_contract", "?")
        fn = getattr(hypothesis, "target_function", "?")
        root_cause = getattr(hypothesis, "root_cause", "")
        target = f"{contract}.{fn}"

        def done(**kw):
            kw.setdefault("elapsed_s", round(time.time() - t0, 4))
            return PathResult(backend=self.name, hypothesis_id=hid, target=target,
                              mechanism=root_cause, **kw)

        if root_cause not in _IN_SCOPE:
            return done(status=PathStatus.OUT_OF_SCOPE,
                        notes=f"structural backend handles {_IN_SCOPE}, not '{root_cause}'")

        modifiers, sinks = self._index(model, contract)
        # Partition entrypoints reaching each sink into guarded / unguarded.
        guarded_of: dict[str, set[str]] = {}
        unguarded_of: dict[str, set[str]] = {}
        for entry, callees in sinks.items():
            is_guarded = bool(modifiers.get(entry))
            for s in callees:
                (guarded_of if is_guarded else unguarded_of).setdefault(s, set()).add(entry)

        # A bypass: a sink reached by an unguarded entrypoint AND a guarded one.
        bypasses = []  # (unguarded_entry, sink, guard_modifiers)
        for sink, unguarded_entries in unguarded_of.items():
            guarded_entries = guarded_of.get(sink)
            if not guarded_entries:
                continue
            guard_mods = sorted({m for g in guarded_entries for m in modifiers.get(g, [])})
            for u in sorted(unguarded_entries):
                bypasses.append((u, sink, guard_mods))
        # Prefer sinks that are protocol-INTERNAL effects (qualified Contract.fn
        # appearing as a caller in the graph) over external token/library calls.
        # The internal effect is the protocol's protected state operation; an
        # external high-level call is a side-effect of many unrelated paths and
        # is weaker auditor signal.
        internal_nodes = {e.get("caller", "") for e in model.get("call_graph", [])}
        bypasses.sort(key=lambda b: (b[0], 0 if b[1] in internal_nodes else 1, b[1]))

        if not bypasses:
            return done(status=PathStatus.NO_PATH,
                        notes="no privileged sink reached by both a guarded and an unguarded entrypoint")

        # Prefer the bypass whose attack entrypoint is the hypothesis target;
        # otherwise report the discovered unguarded sibling for the same cluster.
        chosen = next((b for b in bypasses if b[0] == fn), None)
        note = ""
        if chosen is None:
            # The named target is guarded (e.g. swapAndExecute); Seer pinpoints
            # the unguarded sibling reaching a sink the target's cluster touches.
            target_sinks = sinks.get(fn, set())
            chosen = next((b for b in bypasses if b[1] in target_sinks), None)
            if chosen is None:
                chosen = bypasses[0]
            note = (f"named target {fn} is guarded; Seer pinpointed the unguarded "
                    f"sibling reaching the same privileged effect")

        attacker_fn, sink, guard_mods = chosen
        binding = _GATE_BINDINGS.get((contract, attacker_fn))
        return done(
            status=PathStatus.FOUND, found=True,
            attack_entrypoint=attacker_fn,
            call_sequence=[f"{contract}.{attacker_fn}()", f"-> {sink}()"],
            reaches=[sink],
            guard_bypassed=", ".join(guard_mods) or None,
            gate_binding=binding,
            notes=note or (f"unguarded {contract}.{attacker_fn} reaches {sink} that "
                           f"guarded siblings protect with [{', '.join(guard_mods)}]"))

    # ---- model indexing -------------------------------------------------

    @staticmethod
    def _index(model: dict[str, Any], contract: str):
        """(modifiers per entrypoint fn, sinks per entrypoint fn) for `contract`."""
        modifier_names: set[str] = set()
        modifiers: dict[str, list[str]] = {}
        for f in model.get("entry_points", []):
            if f.get("contract") != contract:
                continue
            mods = f.get("modifiers", []) or []
            modifiers[f["name"]] = mods
            modifier_names.update(mods)

        sinks: dict[str, set[str]] = {fn: set() for fn in modifiers}
        # Build adjacency over ALL edges, then take the sinks each entrypoint reaches
        # TRANSITIVELY. A qualified in-scope callee (Contract.fn) is itself a node with
        # out-edges, so deep flows (ext -> A -> B -> sink) are followed; a bare callee
        # (legacy/leaf) simply terminates. This keeps the saved Decent model (direct,
        # bare) identical while enabling multi-hop reachability on complete graphs.
        adj: dict[str, set[str]] = defaultdict(set)
        for e in model.get("call_graph", []):
            adj[e.get("caller", "")].add(e.get("callee", ""))

        def _reachable(start: str, depth: int = 8) -> set[str]:
            seen: set[str] = set()
            frontier = {start}
            for _ in range(depth):
                nxt: set[str] = set()
                for n in frontier:
                    for c in adj.get(n, ()):
                        if c and c not in seen:
                            seen.add(c)
                            nxt.add(c)
                if not nxt:
                    break
                frontier = nxt
            return seen

        for fn in modifiers:
            for callee in _reachable(f"{contract}.{fn}"):
                if callee in _CALLEE_NOISE or callee in modifier_names:
                    continue
                if callee.endswith("()") and ("." in callee[:-2] or callee[:-2] in ("",)):
                    continue  # library/encoder calls like abi.encode()
                sinks[fn].add(callee)
        return modifiers, sinks
