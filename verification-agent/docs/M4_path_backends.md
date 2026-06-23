# M4 — Path backends (find the path, don't just verify it)

> **State: IMPLEMENTED** (Seer structural reachability) /
> **PARTIAL** (Medusa/Halmos wired, environment-bounded).
> Demo: [`examples/m4_decent_pathfind.txt`](../examples/m4_decent_pathfind.txt)
> (+ coverage map [`.json`](../examples/m4_decent_pathfind.json)).

M4 is where the system has to *discover* paths rather than verify hand-written
ones. Three principles shaped it.

## 1. Reproduce a known path before discovering novel ones

M4's acceptance test is not "find a novel bug" — it's "can Seer independently
rediscover the M-03 path you already know exists?" It can, from the M0 model
alone:

> `_swapAndExecute` is reached by the **guarded** `swapAndExecute` (modifier
> `retrieveAndCollectFees`) **and** by the **unguarded** `receiveFromBridge` (no
> modifier). Seer reports `receiveFromBridge` as the attack path bypassing
> `retrieveAndCollectFees` — without being told.

This is the structural-reachability core ([seer.py](../verification_agent/pathfind/seer.py)):
it searches the call graph for a privileged sink reached by both a guarded and an
unguarded entrypoint; the unguarded one is the concrete bypass. From *any* UTB
access-control hypothesis (including the guarded `swapAndExecute`/`bridgeAndExecute`)
Seer converges on the same answer — the exact thing EV could not separate and the
gate adjudicates.

## 2. Backends serve the predicate

M3 hands each hypothesis a break condition (effects > authorizations). A backend's
job is to find a concrete call sequence that *drives the state to that condition*
— the predicate is the search target, not an afterthought. Seer searches toward
"a privileged effect reached without the authorization enforced elsewhere".
Medusa fuzzes a property harness whose property *is* the invariant, and must find
the sequence that violates it.

The honest per-backend metric: **did this engine produce a path the gate
CONFIRMED?** On Decent, Seer's discovered path is handed to the gate and confirmed:

```
[connect-gate] seer-structural found 'receiveFromBridge' (bypassing retrieveAndCollectFees)
  gate verdict: CONFIRMED
  -> MACHINE-FOUND (Seer, from the model) and MACHINE-VERIFIED (gate, by execution).
```

The path was found by the engine and verified by execution. **What is still
hand-built** is the gate's deployment/invariant scenario (the M1 case) — turning
a discovered path into a fully auto-synthesized PoC (deploy + args + assertion)
is the remaining frontier (M4.5/M5). The *discovery* of which entrypoint breaks
the predicate is now autonomous; the *verdict* is execution. I am not claiming
zero hand-written Solidity anywhere — I am claiming machine-found path + machine
verdict, which is the line between a verifier and a hunter.

## 3. Expect lumpy coverage; log it per-backend, per-mechanism

Symbolic execution times out, fuzzers miss narrow paths, and a structural engine
reaches some mechanisms cleanly and whiffs on others. That is information, not
architectural failure. The orchestrator's product is the coverage map
([orchestrator.py](../verification_agent/pathfind/orchestrator.py)):

```
backends: seer-structural(available), medusa(available), halmos(available)
coverage (per-backend status): seer-structural {found: 6, out_of_scope: 1}
by mechanism: access-control -> found_by [seer-structural]; signature-verification -> (none)
```

Read honestly: Seer reaches the **access-control / reachability** class cleanly
today and correctly declines **signature-verification** (`out_of_scope`) — that
class needs a different engine. That map is what tells you which contests to
enter (mechanisms you can reach) before spending time on a live one.

### Medusa / Halmos status (honest)

Both tools are **installed and available** (Medusa 1.5.1, Halmos 0.3.3) and wired
behind the same interface:

- **Medusa** ([medusa.py](../verification_agent/pathfind/medusa.py)) — a
  cheatcode-free property harness ([DecentFuzzHarness.sol](../verification_agent/pathfind/solidity/DecentFuzzHarness.sol))
  exposes the unguarded entrypoint as a zero-arg action and the invariant as a
  `property_`; the fuzzer must discover that calling it violates the property.
  Invoked with `findpath --run-external`. In this sandbox, whole-project
  crytic-compile + fuzz is heavy and the run is **environment-bounded** (it can
  report `TIMEOUT` within budget) — logged honestly rather than hidden. The
  harness + adapter are the reusable artifact; tuning the budget is M4.5.
- **Halmos** ([halmos.py](../verification_agent/pathfind/halmos.py)) — wired and
  available, but a per-target *symbolic* harness is not yet generated, so it
  reports `OUT_OF_SCOPE` honestly. Symbolic-harness synthesis is M4.5 — the same
  synthesis step the gate's full PoC needs.

The default `findpath` run uses Seer only (fast, deterministic); the external
backends are opt-in via `--run-external` precisely because their coverage is
environment-bounded and should be measured, not assumed.

## The backend wall

Like `kb/` and `hypothesize/`, **nothing in `pathfind/` imports the verify gate**
(enforced by `test_pathfind_does_not_import_the_gate`). A backend finds a path;
the gate alone decides whether it broke the invariant. Discovery makes the agent
a hunter; the gate keeps it honest.

## Run it

```bash
# Seer only (deterministic): find the path, confirm via the gate
python -m verification_agent findpath --model 2024-01-decent.model.json \
       --repo ./2024-01-decent --connect-gate

# also invoke medusa/halmos (slow, bounded) and record their coverage
python -m verification_agent findpath --model 2024-01-decent.model.json \
       --repo ./2024-01-decent --run-external
```

## Scope discipline

Forks and fixtures only — never live targets. M4 is where execution gets real and
"just point it at mainnet to see" is most tempting; that line into the legal grey
zone stays fenced off, as it has for the whole build.
