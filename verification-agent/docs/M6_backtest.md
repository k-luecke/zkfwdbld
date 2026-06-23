# M6 — Backtest harness (the number that says hunter vs verifier)

> **State: IMPLEMENTED.**
> Demo: [`examples/m6_backtest.txt`](../examples/m6_backtest.txt)
> (+ machine-readable [`.json`](../examples/m6_backtest.json)).

M5 makes the output *presentable*; M6 makes it *trustworthy*. The deliverable is
a single, honest measurement: across settled contests in our lane, how often does
the loop **autonomously find a path AND independently verify it** — not how often
it gestures at the right function. Three disciplines make the number un-fudgeable.

## 1. Freeze the taxonomy before the run

The definition of a "catch" is pinned in code ([tiers.py](../verification_agent/backtest/tiers.py))
*before* a single contest is scored — the M6 analog of M1's predicate-author
separation. `classify()` is mechanical: no post-hoc judgment decides whether a
borderline outcome counts.

```
TIER-1  autonomous path + autonomous verdict   (backend FOUND it, gate CONFIRMED it)
TIER-2  TIER-1 + the PoC scenario was machine-synthesized   (M4.5; near-zero today)
TIER-3  surfaced but not caught   (M0 tagged the host; no gate-confirmed path)
MISSED  the host function was not even surfaced
```

The load-bearing detail: **`classify` has no `path_found` parameter.** A path a
backend found but the gate did not confirm is *not* a catch — it is a discovery
*lead*, logged on a separate line. Counting a lead as a catch would reintroduce
exactly the hallucination M1 exists to kill. `FROZEN_RULES` records the
definitions, and [scorer.py](../verification_agent/backtest/scorer.py) `assert`s
them at import, so a later edit that quietly weakens a tier trips an assertion
instead of inflating the headline. The three tiers are logged **separately and
never collapsed** into one number.

## 2. Run it blind

[runner.py](../verification_agent/backtest/runner.py) (`BlindRunner`) executes the
full loop — M0 model → M3 hypotheses → M4 Seer path-finding → M1 gate where a
scenario binding exists — on a contest's **code alone**. It never imports or reads
the published findings. The answer keys live in
[contests.py](../verification_agent/backtest/contests.py) `ANSWER_KEYS` and are
opened **only** by the scorer, **after** the run output is frozen.

- **2024-01-decent** is the **calibration** contest (`blind: False`): M-03 was
  known when its gate case was built, so it is labeled, not counted as a blind win.
- **2023-09-centrifuge** is **blind** (`blind: True`): its M0 model was built from
  the source before these findings were read, and the loop ran against it cold.

## 3. Stay in lane

The contest set is curated to the mechanisms Seer + the gate actually reach
today — **access-control / cross-domain-auth / signature-verification /
reachability / replay / proof-forgery** — not padded with rounding/DoS/accounting
findings that would measure the *gap* instead of the capability. Out-of-lane
findings are still recorded, but excluded from the recall denominator
(`in_lane()`); the lane is named on every scorecard line so the number can't be
quietly widened.

## The frozen scorecard (blind run, this build)

```
[calibration] 2024-01-decent     surfaced= 18  paths= 2  gate_confirmed=1
[BLIND      ] 2023-09-centrifuge  surfaced= 59  paths=16  gate_confirmed=0

================ FROZEN SCORECARD (lane: access-control / cross-chain) ================
in-lane findings across 2 contest(s): 8
  TIER-1 autonomous path + verdict : 1 (recall 0.125)  ids=['M-03']
  TIER-2 fully autonomous (PoC syn): 0 (recall 0.0)   [near-zero until M4.5]
  TIER-3 surfaced not caught       : 5
  surfaced total (tier-3 and up)   : 6 (recall 0.75)
  Seer path-leads on findings      : 3 (NOT catches — leads only)
```

### How to read it (honestly)

- **Tier-1 = 1, and it's the calibration M-03.** On the *blind* contest, Tier-1 is
  **0**. The system surfaces and reasons about the right blind findings, and Seer
  even produces leads on two of them (Centrifuge M-02/M-03), but no gate verdict
  lands — because no machine-synthesized scenario harness exists yet. That is the
  honest headline: **today this is a surfacer + verifier, not yet a blind hunter.**
- **The gap is named, not hidden: it is M4.5 (PoC synthesis).** Tier-2 is 0 by
  construction. The path is machine-found and, on the calibration case, the verdict
  is machine-executed — what is still hand-built is the deploy/args/invariant
  scenario. Close that and the Seer leads become Tier-1 candidates.
- **Surfaced recall 0.75** confirms the M0 structural rule is doing its job: the
  loop *sees* most in-lane findings. The two **MISSED** (Centrifuge M-06/M-08) live
  in auth-guarded / view functions M0 deliberately excludes — the recall/precision
  tradeoff made visible, not papered over.
- **Centrifuge's 16 paths, ~2 landing on real findings.** Seer is a noisy lead
  generator on an unfamiliar codebase; the gate is what would adjudicate the noise.
  This is the EV-gets-to-the-neighborhood / gate-decides-within-it division of
  labor, measured.

**The decision the number drives:** Tier-1 on the access-control class is the
hunter number. It is 1 (calibration) / 0 (blind). So the next move before walking
into a live contest is **build M4.5** (scenario synthesis) to convert the existing
blind *leads* into blind *catches* — not enter a live competition on a verifier's
record.

## Run it

```bash
python -m verification_agent backtest \
    --decent-repo ./2024-01-decent \
    --json examples/m6_backtest.json
```

The runner prints `[BLIND]` / `[calibration]` per contest, freezes the output,
then prints `opening answer keys and scoring` followed by the FROZEN SCORECARD.
The blind separation is structural: the runner cannot read `ANSWER_KEYS`.

## Scope discipline

Every backend stays on forks and fixtures — never live targets — exactly as in
M4. A backtest is run against settled, published contests; nothing here touches a
live deployment or a real balance.
