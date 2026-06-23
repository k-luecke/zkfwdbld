# M0 recall — the structural entry filter

> **State: IMPLEMENTED.** Validated 9/9 on the judged Code4rena 2024-01-decent
> finding set: [`examples/m0_decent_recall.txt`](../examples/m0_decent_recall.txt).

## Why this is the most important number in M0

Recall at the entry point is the system's **discovery ceiling**, and it is the
one error class the verify gate (M1) can never recover. M1 guarantees we won't
*report* garbage; nothing guarantees we *find* the real thing if M0 never
surfaces it. A precision error gets caught downstream — a recall miss at
ingestion is lost silently: no verdict, no error, just a bug nobody looks at.

## The tell, and the fix

The function M0 originally missed was `receiveFromBridge` — the canonical M-03
function this whole project validates against. Name-keyword tagging missed it
because its name dodges every keyword. That is a signal the *method* is too
brittle to be the entry filter, not that one keyword is missing.

The fix is structural and bounded — Slither already provides the facts. A
function is flagged onto the priority surface on **behavioral evidence,
regardless of name**:

> externally reachable **and** state-mutating **and**
> (writes state **or** makes external/low-level calls) **and**
> no auth modifier

implemented in [`surface.tag_structural`](../verification_agent/model/surface.py),
fed by transitive facts (`all_state_variables_written`, `all_high_level_calls`,
`all_low_level_calls`) so a thin delegating entrypoint
(`receiveFromBridge → _swapAndExecute → executor.execute`) is judged on what it
actually reaches. Name keywords are demoted to a **confidence boost**
(`confidence = high` when structural behavior and a keyword surface agree),
never the sole trigger. Constructors and view/pure functions are excluded;
guarded functions (`onlyOwner`, `onlyRouter`, `onlyUtb`, …) are excluded to keep
precision.

This structural rule **is** the M-03 mechanism — "privileged entrypoint
reachable without the auth modifier" — so M0 now tags on the same structural
features M2 retrieves on. The entry filter and the knowledge base align on
mechanism, which is the property you want before M3 reasons across both.

## Validation: the whole finding set, not just M-03

Run over both in-scope foundry projects (`src/` and `lib/decent-bridge`), every
judged High/Medium's host function is on the tagged surface:

| Finding | Host function | Signal |
|---|---|---|
| H-01 | `DcntEth.setRouter` | **structural only** |
| H-02 | `DecentEthRouter.bridge` | high (keyword + structural) |
| H-03 | `DecentBridgeExecutor.execute` | keyword |
| H-04 | `DecentEthRouter.onOFTReceived` | keyword |
| M-01 | `UniSwapper.swapExactIn` | **structural only** |
| M-02 | `DecentEthRouter.bridgeWithPayload` | high |
| M-03 | `UTB.receiveFromBridge` | **structural only** |
| M-04 | `DecentEthRouter.bridge` | high |
| M-05 | `DecentEthRouter.bridgeWithPayload` | high |

**Recall: 9/9.** Three findings (H-01, M-01, M-03) are covered *only* by the
structural signal — name-matching alone surfaces 6/9. The rule generalizes
beyond the one case it was motivated by; it is a method fix, not a patch.

This is also the first recall data point of the backtest: a clean target is
"every function hosting a published High/Medium appears on the surface
automatically", and on this contest it does.

## Honest scope of the claim

This is recall of *host functions onto the surface* — the necessary condition
for the discovery loop to ever look at them. It is not a claim that M0
identifies the bug; that is M3 (hypothesize) and M1 (confirm). The structural
rule deliberately excludes guarded functions, so a bug whose host is correctly
access-controlled but wrong in its internal logic (e.g. H-03's fund-routing in
the `onlyOwner` `execute`) is surfaced here via a *different* signal (keyword) or
would rely on data-flow/fuzzing in M4 — not on the unguarded-entrypoint rule.
The precision cost of the recall bias is over-tagging benign state-changers
(e.g. a plain `contribute()`); that is the intended trade, since a false tag is
cheap and a missed entrypoint is invisible.
