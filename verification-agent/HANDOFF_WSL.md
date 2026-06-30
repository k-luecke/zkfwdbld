# verification-agent — WSL handoff

A standalone brief for the next Claude Code session picking this up inside a WSL2 environment. Read top to bottom once; the **Critical path** section is the minimum to be productive.

---

## Where things live

| Path | What it is |
|---|---|
| `~/zkfwdbld/` | Main repo clone, currently on `master` with **unrelated uncommitted work** in `src/r1cs.rs`, `src/witness_gen.rs`. **Do not touch.** |
| `~/zkfwdbld-va/` | Git **worktree** of the same repo, checked out to branch `claude/verification-agent-build-aggdnj`. All verification-agent work happens here. |
| `~/zkfwdbld-va/verification-agent/` | The Python subproject this handoff is about. |
| `~/zkfwdbld-va/verification-agent/.venv/` | Virtualenv (Python 3.12) created via `uv venv`. Contains slither 0.11.5, solc-select 1.2.0, web3, etc. |

`solc 0.8.20` is installed globally via `solc-select` (lives under `~/.solc-select/`).

`forge` lives at `~/.foundry/bin/forge` and is on PATH.

---

## Critical path: pick up where the last session left off

```bash
# 1. Activate the existing env
cd ~/zkfwdbld-va/verification-agent
source .venv/bin/activate

# 2. Confirm tools
forge --version | head -1
slither --version
solc --version | head -1   # should be 0.8.20

# 3. Run the test suite (should be 80/80 green)
pytest -q -m "not needs_tools"
```

If 80/80 still passes, the environment is intact. The state is exactly as I left it.

---

## Branch state (as of this handoff)

Branch: `claude/verification-agent-build-aggdnj`

Latest pushed commits:

```
be99c40 verification-agent: whole-program call graph (multi-hop) + CI
1d321a2 verification-agent: qualify scorer identifiers; refresh CLI docstring
38e2063 Screening tools: Move A (shape-fit screen) + Move B (judged-findings fetch/parse)
```

**Uncommitted changes** (these are real fixes from running the live-Slither validation; deliberately left for the user to review before commit):

```
verification-agent/examples/2024-01-decent.model.json   ← regenerated against live target
verification-agent/tests/test_pathfind.py               ← qualified-effect assertion
verification-agent/tests/test_protocol_rules.py         ← qualified-effect + IR-noise assertion
verification-agent/verification_agent/model/slither_runner.py  ← _hlc_name fix for slither >= 0.10 IR tuples
verification-agent/verification_agent/pathfind/seer.py  ← prefer internal-qualified sinks in bypass tie-break
```

See the **Slither validation findings** section below for the why on each.

---

## Slither validation findings (what the live regen surfaced)

The prior session's whole-program-call-graph fix (commit `be99c40`) was unit-tested with a duck-typed fake Slither because the sandbox lacked the real toolchain. Running it for the first time against the live Decent target on a tool-provisioned machine surfaced two real defects:

### 1. `_hlc_name` IR-string leak (real bug — fixed in working copy)

**Symptom**: high-level edges in the regenerated model contained slither's raw IR-Operation string, e.g.:

```json
{"caller": "UTB.performSwap",
 "callee": "ISwapper.TUPLE_1(address,uint256) = HIGH_LEVEL_CALL, dest:swapper(ISwapper), function:swap, arguments:['REF_19']",
 "external": true}
```

**Root cause**: in slither `>= 0.10`, `func.high_level_calls` returns `(Contract, HighLevelCall-IR-Operation)` tuples. The target function name is at `op.function.name`, not `op.name` (which is `None`). The old code's `getattr(function, "name", None) or str(function)` fell through to `str(op)` and dumped the entire IR string into the edge.

**Fix** (`slither_runner.py:_hlc_name`): read `op.function.name` first, fall back to `op.name` for older slither variants, return `None` if neither resolves (drops the edge rather than poisoning it).

After fix: 0 IR-leak edges, 50 clean high-level edges like `IERC20.transferFrom`, `ISwapper.updateSwapParams`.

### 2. Seer tie-break preferred external token calls over internal protected effects (signal-quality regression — fixed)

**Symptom**: with the now-richer call graph, Seer's M-03 report changed from `reaches=['_swapAndExecute']` to `reaches=['IERC20.approve']` because the bypass had ~10 shared sinks and the alphabetical tie-break picked the external token call.

**Why this matters**: an auditor wants "the bypass lets the attacker reach a protected protocol-internal effect", not "the bypass lets the attacker reach an ERC20 transfer" — the latter is a side-effect of many unrelated paths.

**Fix** (`seer.py`): sort `bypasses` by `(unguarded_entry, 0_if_internal_else_1, sink)`. Internal-qualified sinks (those appearing as callers in the graph) are now reported preferentially. Restores the M-03 report to `reaches=['UTB._swapAndExecute']`.

### 3. Two test assertions made brittle by the richer graph (updated — by design)

- `test_pathfind.py::test_seer_rediscovers_m03_path`: now asserts the reached sink is one of `{UTB._swapAndExecute, UTB.performSwap}` — the qualified internal effects M-03 traverses — instead of bare `_swapAndExecute`.
- `test_protocol_rules.py::test_decent_keeps_m03_as_a_claimed_rule_violation`: now asserts that *some* `UTB.receiveFromBridge` violation has `effect ∈ {UTB._swapAndExecute, UTB.performSwap}`, instead of pinning the first one (the extractor now correctly emits both, since both are shared with the guarded sibling).
- `test_protocol_rules.py::test_trivial_shared_callees_are_not_treated_as_effects`: the old assertion `"." not in v.effect` was an IR-string proxy; that's now wrong because qualified internal effects legitimately contain `.`. Replaced with explicit IR-string checks (`"HIGH_LEVEL_CALL" not in`, `"TUPLE_" not in`).

These are all honest test updates, not assertions weakened to fit a broken implementation — the qualified form is more correct than the old bare-name form, and `_swapAndExecute` + `performSwap` are both genuine shared internal effects under M-03.

### End-to-end validation (passes)

```
M-03 PATH RESOLVED:
  attack_entrypoint = receiveFromBridge
  reaches           = ['UTB._swapAndExecute']
  guard_bypassed    = retrieveAndCollectFees
  gate_binding      = DecentReceiveFromBridgeBypass
  call_sequence     = ['UTB.receiveFromBridge()', '-> UTB._swapAndExecute()']
```

Test suite: **80 passed in 0.73s** on the freshly-regenerated model.

---

## Decision pending: commit & push

The five uncommitted file changes belong logically as one commit on top of `be99c40`. Suggested commit message:

```
verification-agent: live-Slither validation — fix _hlc_name IR leak,
prefer internal sinks in Seer tie-break, regenerate Decent model

The whole-program call-graph fix (be99c40) was unit-tested with a fake
Slither because the sandbox lacked the toolchain. Running it for the
first time against the live 2024-01-decent target surfaced:

* _hlc_name: slither >= 0.10 returns (Contract, HighLevelCall-IR-Op)
  tuples; the target Function is at op.function, not op.name. The old
  `or str(op)` fallback was leaking the entire IR Operation string
  into edges. Fixed by reading op.function.name with op.name fallback.

* Seer bypass tie-break: with the richer transitive graph, the
  alphabetical tie-break preferred external token calls (IERC20.approve)
  over protocol-internal effects (UTB._swapAndExecute). Internal sinks
  are the right auditor signal; sort by (entry, is_internal, sink).

* Tests: assertions previously pinning bare _swapAndExecute now accept
  the qualified UTB._swapAndExecute / UTB.performSwap (both are real
  M-03 effects shared with the guarded sibling). The "." not in v.effect
  noise check was an IR-string proxy; replaced with explicit checks.

End-to-end: M-03 resolves with attack_entrypoint=receiveFromBridge,
reaches=['UTB._swapAndExecute'], guard=retrieveAndCollectFees. 80/80.
```

The previous session committed under the Claude identity (`Claude <noreply@anthropic.com>`). For your own work, the current `git config user.email` is `kyle_w_luecke@users.noreply.local`. Decide which identity should land this commit before pushing.

Signing: the previous session's two tip commits are SSH-signed via the environment's configured `commit.gpgsign`. Locally signed commits appear `N` (unverified) via `git log --show-signature` because there's no `allowedSignersFile`, but GitHub verifies them against Anthropic's registered key. On WSL, ensure `git config commit.gpgsign` and `gpg.format` / `user.signingkey` match whatever signing scheme you want.

---

## Environment quirks to know about (WSL specifically)

- **System Python has no pip or venv**: Ubuntu 24.04 on WSL ships `python3` but not `python3-pip` or `python3-venv` by apt-default. The project uses `uv` (installed at `~/.local/bin/uv`) to get around this — `uv venv` + `uv pip install -e ".[dev]"` works without sudo.
- **Foundry is at `~/.foundry/bin/`** — already on PATH via `.bashrc`.
- **solc-select state** lives at `~/.solc-select/`. The currently-selected version is global, not per-project. If you `solc-select use 0.8.NN` for a different target, remember to switch back before regenerating the Decent model.
- **`forge build` for the Decent target downloads via git submodule** and writes a lot to `out/`, `cache/` — the model builder uses a temp workdir, so this doesn't pollute the repo.

---

## Running CLI commands by hand

The most useful workflows:

```bash
cd ~/zkfwdbld-va/verification-agent
source .venv/bin/activate

# Build a target model (M0)
python -m verification_agent model --repo https://github.com/code-423n4/2024-01-decent \
  --commit 5d1962143ee566e7f9354b735bff3492b8f82761 \
  --out examples/2024-01-decent.model.json

# Rank hypotheses against a model (M3)
python -m verification_agent hypothesize --model examples/2024-01-decent.model.json --top 10

# Run pathfinding (M4); --run-external invokes medusa/halmos and is slow
python -m verification_agent findpath --model examples/2024-01-decent.model.json

# Backtest harness (M6) — frozen three-tier scorecard
python -m verification_agent backtest

# Shape-fit pre-screen (Move A)
python -m verification_agent screen --model examples/2024-01-decent.model.json

# Knowledge-base query (M2)
python -m verification_agent kb --query "access-control"
```

`python -m verification_agent --help` lists all subcommands. Implementation maturity per subcommand is labeled honestly in `STATUS.md`.

---

## What's actually in this subproject (one-paragraph orientation)

`verification-agent` is the autonomous, human-supervised vulnerability-finding agent on the "verify-or-discard" thesis: candidate findings only count after the M1 truth gate confirms the specific invariant break. The M1 gate (`verify/`) is the strongest component — clean four-phase structure (baseline / control / attack / confirm). Discovery (`hypothesize/`, `pathfind/`, `screen/`) is structurally walled off from `verify/` (enforced by test assertions in each module). Reasoning over Slither's output happens in `model/slither_runner.py` and is downstream-consumed by `pathfind/seer.py` (structural-reachability backend) and `hypothesize/protocol_rules.py` (modifier-asymmetry rule extraction). The backtest harness (`backtest/`) runs against frozen answer keys from Code4rena. See `STATUS.md` for per-module maturity.

---

## Open follow-up items from the prior review (not done in this pass)

These came from a static code review of the subproject; the previous session shipped #1 (call graph), #3 (qualified scorer identifiers), and #6 (CLI docstring), plus a CI job. Still open:

| # | Issue | Severity | Notes |
|---|---|---|---|
| 2 | Modeling live targets executes untrusted project code without sandboxing notes | High | The agent clones arbitrary repos, runs `forge build`, `npx hardhat compile`, `git submodule init`. Document the threat model in `README.md` and recommend disposable container/VM with network+filesystem isolation. Verify/synth runners already have timeouts; clone/build/modeling should get the same discipline. |
| 4 | Backtest headline mixes calibration and blind contests | Medium | `score_contest()` aggregates both; should split scorecard into calibration / blind / combined with blind first, since the project's core selling point is honest state labeling. |
| 5 | README terminology conflicts: "Nothing unverified is ever surfaced" vs "Tier-3 surfaced not caught" | Medium | Reserve "reported finding" for confirmed outputs; use "lead", "surface hit", "candidate host" before M1 confirmation. |
| 7 | Python dependency reproducibility is loose | Medium | `pyproject.toml` uses `>=` ranges; for a verification tool, tool versions materially affect results. Add a lockfile or constraints file, and include Slither / solc / Foundry / Medusa / Halmos versions in run artifacts. |

---

## Sanity-test the validation worked

If anything in the environment seems wrong, run these in order to localize the breakage:

```bash
cd ~/zkfwdbld-va/verification-agent && source .venv/bin/activate

# 1. Tooling
which forge slither solc

# 2. Pure-Python tests (no external tools)
pytest -q -m "not needs_tools"             # expect: 80 passed

# 3. Round-trip the Decent model regen
python -m verification_agent model \
  --repo https://github.com/code-423n4/2024-01-decent \
  --commit 5d1962143ee566e7f9354b735bff3492b8f82761 \
  --out /tmp/decent.check.json
python3 -c "
import json
m = json.load(open('/tmp/decent.check.json'))
bad = [e for e in m['call_graph'] if 'HIGH_LEVEL_CALL' in (e.get('callee') or '')]
qual = sum(1 for e in m['call_graph'] if '.' in (e.get('callee') or ''))
print(f'edges={len(m[\"call_graph\"])}  qualified={qual}  IR-leak={len(bad)}')
assert len(bad) == 0 and qual > 100, 'regression vs. validated state'
print('OK')
"

# 4. M-03 end-to-end
python3 -c "
import json
from verification_agent.hypothesize import HypothesisEngine
from verification_agent.pathfind import SeerStructuralBackend
m = json.load(open('examples/2024-01-decent.model.json'))
for h in HypothesisEngine().run(m):
    if h.target_contract == 'UTB' and h.root_cause == 'access-control':
        r = SeerStructuralBackend().find_path(h, m)
        if r.found and r.attack_entrypoint == 'receiveFromBridge':
            assert r.guard_bypassed == 'retrieveAndCollectFees'
            assert r.gate_binding == 'DecentReceiveFromBridgeBypass'
            assert 'UTB._swapAndExecute' in r.reaches
            print('M-03 OK')
            break
"
```

---

## One-line summary

Worktree at `~/zkfwdbld-va` on branch `claude/verification-agent-build-aggdnj`; venv ready; 80/80 tests pass; M-03 resolves end-to-end with the qualified internal sink. Five uncommitted file changes are the live-Slither validation fixes — review and commit at your convenience.
