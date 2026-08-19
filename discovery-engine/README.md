# Discovery engine

One registry, many lanes, running unattended. It surfaces candidates, judges them
with oracles that the generator cannot argue with, and puts only survivors in
front of a human.

**The one invariant, executable:** a lane may run unattended **iff** it is
human-validated **and** has a machine-checkable oracle. Everything else is
registered as refused and logged — never faked.

**The second invariant, which makes the first one true in practice:** an oracle
that could not *run* does not get to say PASS. Missing tooling yields
`INCONCLUSIVE` plus a reason, counted in its own column. *Nothing found* and
*nothing ran* must never look alike.

## Build state — read this before trusting any output

| Piece | State | Notes |
|---|---|---|
| Refusal invariant (riddles I, II, VIII) | **WORKING** | Registered, ineligible, logged to `state/refused_log/`. Verified by tests. |
| Lane registry + eligibility rule | **WORKING** | `validated AND oracle`, no override flag. |
| Storage boundary (git vs Drive) | **WORKING** | Atomic writes, pointer-only in git, and a hard refusal to put bulk bytes in the tree. |
| Headless generator plumbing | **WORKING** (parsing + failure modes) / **UNEXERCISED** (no live run yet) | A broken pipe raises; it can never impersonate "found nothing". |
| VerifyGate oracle | **WIRED, NOT YET EXECUTED** | Adapter calls the real `verification_agent.verify` harness next door; the harness and its 5-case registry import cleanly. **Needs Foundry** — `forge` is absent wherever `discovery status` says NOT RUNNABLE HERE, and the M1 smoke test has **not** been run. |
| Andersen-2019 rubric (study 001) | **PRESENCE FLOOR** | Checks each control is *reported*, not that it clears a quantitative bar. Every record says `PRESENCE_FLOOR`. Graded scoring is Prompt 2 and needs the paper's thresholds in hand; inventing bars would be guessing. |
| study001 literature puller | **SEAM ONLY** | Prompt 2. |
| study002 deception probe | **SEAM ONLY**, honest abort implemented | A non-held-out adversary is `INCONCLUSIVE`, never PASS, however good the AUROC. |
| Timers, sandboxed user, auto-push | **NOT DONE** | Prompt 3 — needs the compute host. |
| Phone intake action, rclone mount | **NOT DONE** | Prompts 4 and 5. |

`blind_precision` is **UNMEASURED** until the Sequence blind run executes. Every
queued record carries that word. Do not tune anything against a yield that has
not been measured.

## The two human touchpoints

Both are review. Neither is build.

1. **Contract re-audit** — three-field bidirectional, on `state/human_queue/`:
   host function correct, bug class correct, adversary actually exists; then the
   reverse pass for omitted findings.
2. **Riddle floor-validation** — the four-corners/ceiling/floor form, on
   `state/riddle_drafts/`. Validate a riddle once; from then on its lane runs
   forever. Only a riddle with a *named oracle* becomes an eligible lane.

Everything else is the engine's job, forever.

## How the three points connect

**Git is the sync.** Not a Claude feature — this repo is the single source of
truth. Nothing magic crosses devices; committed files do.

| Point | Role | Runs the engine? |
|---|---|---|
| Compute host (Ubuntu, 24/7) | Timers run lanes, auto-commit results, push. | **Yes — the only one** |
| Phone | Intake + review. File a target; read the queues in GitHub mobile. | No |
| Browser / claude.ai project | Judgment. Validate drafted riddles, discuss results. | No |

The review queues are files in `state/`, tracked in git. The push after each run
**is** the cross-device sync.

## Layout

```
paths.py                the storage boundary: git holds control state, Drive holds bulk
headless.py             the one place that shells out to `claude -p`
verifygate_adapter.py   the real seam to verification_agent.verify (four-phase gate)
moe_orchestrator.py     router -> expert surfacers -> gate -> queue
discovery_engine.py     lanes, oracles, registry, the unattended pass, the drafter
cli.py                  status / run / draft / queue / gate-selftest
state/                  TRACKED control state — this is the sync
  human_queue/          gate-passed items awaiting your acceptance decision
  riddle_drafts/        proposed riddles awaiting your floor-validation
  refused_log/          lanes the engine declined to run, with reasons
  runs/                 one report per pass
  targets.json          {repo_path: [surface_tags]}
tests/                  the invariants, executable
```

## Use

```bash
python3 cli.py status              # what is wired, what is refused, what is missing
python3 cli.py run --dry-run       # dispatch plan; spends no headless call
python3 cli.py run                 # one unattended pass  (discovery-run.timer)
python3 cli.py draft               # propose riddles      (discovery-draft.timer)
python3 cli.py queue               # read both review queues
python3 -m pytest                  # 45 tests: the invariants
```

`state/` is the default control root because that is what makes the queues
reviewable from a phone. Set `MOE_ROOT` to relocate it (e.g. `MOE_ROOT=~/moe`).
Set `DRIVE_DIR` to the Drive-backed path for bulk artifacts; `put_artifact()`
refuses to write bulk bytes anywhere inside the git tree.

### The gate's prerequisites

The contract lane's oracle fork-executes Solidity, so the compute host needs
Foundry and the verification-agent package:

```bash
curl -L https://foundry.paradigm.xyz | bash && foundryup
pip install -e ../verification-agent
python3 cli.py gate-selftest --repo /path/to/2024-01-decent   # the M1 smoke test
```

`gate-selftest` runs the M1 five-case registry: one real judged finding (C4
2024-01-decent M-03) that must CONFIRM, and four constructed controls the gate
must reject — a false hypothesis, a wrong-reason PoC, and two malformed
*predicates*. `ok: true` means the gate confirmed the real one and rejected all
four. Anything else means do not trust that night's run.

**This smoke test has not been executed yet** — it needs Foundry and a decent
checkout. Run it before the first live pass. It is Prompt 1, step 3.

## Why a hypothesis is not a finding

Three walls, all enforced in code rather than in prose:

- **Predicate-author separation.** `gate()` deletes `self_verdict`, `confidence`,
  and every other self-assessment field before judging. The generator does not
  get a vote in its own trial.
- **A hypothesis is not a runnable case.** The gate judges compiled Solidity. A
  lead with no scenario returns `no_runnable_case` / `INCONCLUSIVE` — never
  CONFIRMED, and never silently dropped as though it had been tested. Turning a
  lead into a scenario is M4.5 synthesis.
- **The drafter cannot register a lane.** Predicate-author separation at the meta
  level: the thing that proposes frontier problems does not get to certify that
  their floors are real. A test walks the drafter's AST to keep it that way.

## Next, in order

Prompt 0 (this commit) proves the engine refuses to fake a riddle before it is
allowed to run anything. Then:

1. **Prompt 1** — install Foundry, run `gate-selftest`, add a known target to
   `targets.json`, confirm a known finding reaches `human_queue`.
2. **Prompt 2** — graded Andersen scoring + the literature puller.
3. **Prompt 3** — the `moe` user, the two systemd timers, and the auto-push that
   makes the queues visible from the phone.
4. **Prompt 4** — issue-based intake from the phone.
5. **Prompt 5** — rclone/`DRIVE_DIR` for bulk corpora.

Do not reorder. The refusal check is the thing that keeps this from becoming the
artifact you would tear down.
