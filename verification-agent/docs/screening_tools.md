# Screening tools (Move A + Move B) — pick the right target, then score it

Two bounded infrastructure tools that came out of the Kelp blind run. They are
*tooling*, not a hunt: Move A selects a target by bug-class shape; Move B lets a
blind run be scored. Neither runs or chases a catch.

## Move A — shape-fit screen (the Kelp lesson, codified)

Kelp produced no catch because it was screened as an "access-control protocol" —
too loose. The screener
([screen/shape.py](../verification_agent/screen/shape.py)) instead scores a codebase
for the **alt-entrypoint shape** the loop actually catches — a permissionless path
reaching an effect a sibling *gates* — from **code structure alone**. It runs the
M0 structural surface + the Move-2 sibling-asymmetry signal + Seer's reachability as
a pre-screen.

The decisive signal is **Seer-pathability**, not candidate count. On the two
contests with ground truth:

| Contest | candidates (Move-2) | Seer-pathable | band | shape_fit |
|---|---|---|---|---|
| **Decent** | 4 | **3** (incl. M-03) | **HIGH** | 0.9 |
| **Kelp** | 7 | **0** | **LOW** | 0.2 |

Kelp has *more* candidates but zero are attacker-reachable bypasses (they are
initializer/unpause asymmetries) — so the screen correctly calls it LOW. The screen
**never reads judged findings** (that would break blindness); shape-fit is a function
of the structural model, so it runs identically on a **live competition's scope** —
the dual-use contest-selection tool.

```bash
python -m verification_agent screen --model examples/2024-01-decent.model.json   # HIGH
python -m verification_agent screen --model examples/2023-11-kelp.model.json       # LOW
python -m verification_agent screen --local ./path/to/live-scope                   # build + screen
```

## Move B — judged-findings fetch + parse (so a blind run can be scored)

A blind run can only be scored against the contest's judged H/M findings, which live
in Code4rena's public `<contest>-findings` repos (`report.md`), reachable by git.
[screen/findings.py](../verification_agent/screen/findings.py) fetches that report and
parses it into the scorer's ANSWER_KEYS format `(id, title, mechanism, severity,
hosts)`.

Validated on the **real** 2024-01-decent report: all 9 judged findings recovered, ids
matching the hand-curated answer key exactly. **id / title / severity are parsed
exactly**; **hosts and mechanism are best-effort heuristics** (regex over code refs;
keyword classification) — flagged as derived, for a human to refine (e.g. a URL can
leak into a host on a noisy body).

```bash
python -m verification_agent answer-key --contest 2024-01-decent --json key.json
# offline? supply a saved report, never fake retrieval:
python -m verification_agent answer-key --contest <id> --report ./report.md
```

**The wall is intact.** Move B *writes* answer keys and runs only **after** a blind
run is frozen; the `BlindRunner` still cannot read answer keys (asserted by
`test_blindrunner_wall_does_not_read_answer_keys`). Fetch never feeds the run.
