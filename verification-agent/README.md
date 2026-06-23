# Verification-Agent

An autonomous, human-supervised vulnerability-finding agent specialized for
**verification, reachability, and cross-chain / ZK scopes** — the bug classes
commodity AI auditors miss (signature/proof verification, merkle/state-proof
checks, bridge message handling, cross-domain auth, slashing/AVS state machines).

> **Core discipline — verify-or-discard.** Every reported finding is
> fork-executed into a runnable PoC before it counts. Nothing unverified is ever
> surfaced. Eliminating hallucinated findings is the product.

This repository is being built as a **walking skeleton**: each milestone runs
end-to-end before the next is started, proven against already-settled audit
contests at every step. See [STATUS.md](STATUS.md) for the honest, per-module
build state.

## What's built today: **M0 — the harness**

M0 ingests a target and emits a single JSON **target model** that every
downstream stage consumes:

- clone a scope repo at a pinned commit;
- detect the build system (**Foundry** first-class, Hardhat fallback) and compile;
- run **Slither** to extract contracts, inheritance linearization, entry points,
  storage variables, and the call graph (internal + external-call edges);
- apply the **specialization filter**: tag every entry point that touches the
  verification / reachability / cross-chain / ZK surface as PRIORITY, with the
  exact evidence that triggered each tag so a human can audit the heuristic;
- flag on **mechanism, not name**: a structural rule catches any unguarded
  privileged entrypoint (state-mutating + external calls + no auth modifier)
  even when its name dodges every keyword — closing the entry-point recall gap.
  On the judged 2024-01-decent set this surfaces **9/9** finding hosts (6/9 by
  keywords alone); see [docs/M0_recall.md](docs/M0_recall.md).

## And: **M1 — the verify gate (the truth gate)**

The differentiator. **A finding is surfaced only if it is fork-executed into a
reproducing PoC** — and the gate proves the *specific claimed invariant break*,
not merely that "a test passed". Each case defines an invariant predicate,
defined independently of the attack; the gate decides the verdict across four
phases (baseline → control → attack → re-check), so the PoC author cannot
self-certify.

Proven on `2024-01-decent` with three cases — the recorded run is
[`examples/m1_decent_gate_run.txt`](examples/m1_decent_gate_run.txt):

Five cases exercise every corner of the verdict taxonomy — bad *exploits*
(A–C) and bad *predicates* (D–E, the gate auditing its own measuring stick):

| Case | What it is | Verdict |
|---|---|---|
| known-true | the real **C4 M-03** `receiveFromBridge` fee/signature bypass | **CONFIRMED** |
| false hypothesis | a forged signature "passes" `collectFees` (it reverts) | rejected — not reproduced |
| **wrong-reason** | a fully-**paid** swap claimed as a bypass: state changes, but the fee *is* paid | rejected — invariant intact |
| malformed baseline | a predicate that is false at rest | rejected — bad measuring stick |
| malformed control | a predicate any honest action breaks | rejected — bad measuring stick |

The wrong-reason case separates this gate from a hallucinating auditor: the
transaction succeeds and changes on-chain state, yet the gate refuses to confirm
because the stated invariant was not violated. The two malformed cases prove the
Control/Baseline guards *fire* — so the soundness of every `CONFIRMED` rests on
tested guards, not faith. Full design and soundness argument:
[docs/M1_verify_gate.md](docs/M1_verify_gate.md).

## And: **M2 — the knowledge base (hypothesis priors)**

The discovery layer's grounding. Lane-curated (verification / cross-chain / ZK),
**mechanism-structured** so retrieval keys on bug-*class* not vocabulary, and
**dual-source**: OAK taxonomy (what kinds of attacks exist) kept distinct from
contest/incident worked examples (how they manifested), blended at query time
with provenance tagged.

Querying the **M-03 surface** returns the real M-03 finding and the *same
bug-class* across OAK + other protocols (Poly Network, DcntEth) at the top; a
deliberate "bridge fee rounding" **vocabulary decoy** ranks **#18 of 20**.
Recorded demo: [`examples/m2_kb_m03_query.txt`](examples/m2_kb_m03_query.txt).

Bright boundary, consistent with the gate: **a prior is never a verdict.**
`PriorMatch.is_verdict` is `False` by construction; a retrieved finding is a
reason to *run the gate*, never to surface a finding. The retrieval makes the
agent fast; the gate keeps it honest. Design: [docs/M2_knowledge_base.md](docs/M2_knowledge_base.md).

## And: **M3 — the hypothesis engine (proposes; never confirms)**

The discovery loop's reasoning core. It connects M0's surface and M2's priors
into EV-ranked **candidate** hypotheses whose primary output is a
**gate-survivable invariant predicate**.

- **Proposes, never confirms** — a structural wall, not discipline. A
  `Hypothesis` has no verdict field, `is_candidate` is always `True`, the LLM's
  confidence carries **zero weight** on any verdict, and **nothing in
  `hypothesize/` imports the gate** (enforced by a test). The LLM aims the gate;
  it never vouches for what it aims at.
- **The predicate is the product** — each hypothesis carries an invariant with
  explicit baseline/control/break expectations. On the Decent surface the
  gate-bound M-03 predicate (`count(privileged-effect) == count(authorized)`) is
  exactly the M1 gate's invariant; handed to the gate it **clears baseline +
  control and returns CONFIRMED**. The discovery layer and the truth gate are
  connected.
- **EV earns its keep** against M0's over-inclusive surface: a blast-radius
  factor sinks the benign `contribute()` to the EV floor below every real
  function. EV gets you to the right neighborhood; the gate adjudicates within
  it. Design: [docs/M3_hypothesis_engine.md](docs/M3_hypothesis_engine.md).

## And: **M4 — path backends (find the path, not just verify it)**

Where the system has to *discover* paths. The **Seer** structural-reachability
engine searches the M0 call graph toward the break predicate — a privileged sink
reached by both a guarded and an unguarded entrypoint — and **independently
rediscovers the M-03 path** (`receiveFromBridge` bypassing
`retrieveAndCollectFees`) from the model alone. Handed to the M1 gate it
**CONFIRMS**: machine-found path, machine verdict.

```
[seer] attack entrypoint: receiveFromBridge  reaches [_swapAndExecute]  bypasses [retrieveAndCollectFees]
[connect-gate] -> gate verdict: CONFIRMED  (machine-found, machine-verified)
```

**Medusa** (1.5.1) and **Halmos** (0.3.3) are installed and wired behind the same
interface; their coverage is environment-bounded and **logged honestly** in a
per-backend, per-mechanism map (`findpath --run-external`). The orchestrator
reports which engine reaches which bug class today — Seer reaches access-control/
reachability cleanly and correctly declines signature-verification. Same wall as
the rest: **nothing in `pathfind/` imports the gate** (enforced by a test).
Honest scope: the *path discovery* is autonomous; auto-synthesizing the full PoC
scenario (deploy + args) is the remaining frontier. Design:
[docs/M4_path_backends.md](docs/M4_path_backends.md).

## And: **M4.5 — scenario synthesis (turn a found path into a verdict)**

The component the backtest named: it synthesizes the gate scenario (deploy +
invariant + control + attack) from a Seer lead, using a **target-agnostic**
template (no protocol names — a `CONFIRM` can't be smuggled in), and runs it
through the **byte-for-byte real** gate with **no fast path**. Because generation
is where hallucination re-enters, the discipline holds hardest here, and it is
*proven*, not asserted — from every lead the synthesizer emits a faithful **and**
a deliberately rigged scenario:

```
[lead] receiveFromBridge  (bypasses retrieveAndCollectFees)
   [OK ] faithful       -> CONFIRMED                    (the unguarded sibling breaks the invariant)
   [OK ] rigged-control -> REJECTED_MALFORMED_CONTROL   (a machine-rigged predicate; Control catches it)
```

That second line is the guarantee: a machine that writes a rigged scenario is
rejected exactly as a human's would be.

**Deploy-graph synthesis** (the next layer) derives a target's collaborator
deploy+wiring from the M0 model alone; spliced into a hand-built semantic mile it
**CONFIRMS Decent M-03 against real code** (calibration). But the honest ledger is
the result, not the green check: the machine backbone is **5 of 6 lines autonomous**
(one needs a hand-fix — Slither drops a `payable` qualifier) and a *minority* of a
confirming scenario. So the frontier is **sharpened, not closed**: "deploy graph"
was the tractable part; the real distance is the **semantic mile** — mock
behaviour, call payloads, and the core blocker, **autonomous signature construction
for the honest Control**.

The **signature keystone** then closes the named core blocker: `SignatureSchemeSynthesizer`
reads the verifier's source, **detects** the scheme (EIP-191 personal_sign), and
**constructs** the Control's signature — no hand sig anywhere. Spliced with the
deploy-graph backbone it **CONFIRMS Decent M-03 against real code**, and a *wrong*
scheme reverts Control (`REJECTED_MALFORMED_CONTROL_REVERT`) — the guard fires, proven
not asserted. Full-scenario autonomy moved **19% → 31%**. This is a real autonomous
true-positive CONFIRMED — **calibration, not blind**. (EIP-712 is detected-but-not-emitted:
the permit/signature-scope frontier transfers in shape, not yet coverage.)

**An honest negative result** is kept first-class: the surfaced structural
Centrifuge leads were **refuted against real code** (deploy the real `Root`, run the
unchanged gate → `REJECTED_ATTACK_REVERTED`) — they are design-permissionless
functions, not bypasses. So **blind Tier-1 stays 0**, but the reason is a *bug-class
coverage* gap, not a synthesis gap — and the next blind structural target is a
different contest, not Centrifuge. Design + ledger:
[docs/M4.5_scenario_synthesis.md](docs/M4.5_scenario_synthesis.md).

## And: **M6 — the backtest (the number that says hunter vs verifier)**

M6 turns the loop loose on **settled** contests and measures it against a
taxonomy **frozen before the run** — the M1 predicate-author separation applied to
scoring. Three tiers, logged separately and never collapsed: **Tier-1** =
autonomous path **and** autonomous verdict; **Tier-2** = +machine-synthesized PoC
(M4.5); **Tier-3** = surfaced but not caught. `classify()` has no `path_found`
parameter on purpose — **a found path the gate did not confirm is a *lead*, not a
catch.** The runner is **blind** (it cannot read the answer keys; the scorer opens
them only after the output is frozen), and the contest set stays **in lane** —
access-control / cross-domain / signature — rather than padded with rounding/DoS.

```
================ FROZEN SCORECARD (lane: access-control / cross-chain) ================
in-lane findings across 2 contest(s): 8
  TIER-1 autonomous path + verdict : 1 (recall 0.125)  ids=['M-03']   # the calibration finding
  TIER-2 fully autonomous (PoC syn): 0 (recall 0.0)    [near-zero until M4.5]
  TIER-3 surfaced not caught       : 5
  surfaced total (tier-3 and up)   : 6 (recall 0.75)
  Seer path-leads on findings      : 3 (NOT catches — leads only)
```

The honest read: on the **blind** contest (Centrifuge 2023-09) Tier-1 is **0** —
the loop surfaces the right findings (recall 0.75) and Seer even produces leads on
two, but no machine-built scenario harness exists to turn a lead into a verdict.
**Today this is a surfacer + verifier, not yet a blind hunter; the named gap is
M4.5 (PoC synthesis).** That is the number that says *build M4.5 before walking
into a live contest*. Design: [docs/M6_backtest.md](docs/M6_backtest.md).

Triage + report (M5) is next, built on top of this measured baseline. The build
order is load-bearing: the gate was trusted, then everything upstream proven
against it, before the output was ever scored.

## Usage

```bash
pip install -e .            # installs slither-analyzer + solc-select
# Foundry (forge/anvil) must be on PATH: https://book.getfoundry.sh/

# Build the model for a settled contest, pinned to a commit:
python -m verification_agent model \
    --repo https://github.com/code-423n4/2024-01-decent \
    --commit 5d1962143ee5 \
    --out model.json

# Or model an existing local checkout (skips cloning):
python -m verification_agent model --local ./path/to/checkout --out model.json

# M1: run the verify-gate self-proof against a cloned target:
python -m verification_agent verify --repo ./path/to/2024-01-decent

# M2: query the knowledge base for hypothesis priors:
python -m verification_agent kb --demo
python -m verification_agent kb --surface bridge_inbound_handler --text "receiveFromBridge"

# M3: rank candidate hypotheses for a target model (and hand the top to the gate):
python -m verification_agent hypothesize --model model.json --top 10
python -m verification_agent hypothesize --model 2024-01-decent.model.json --connect-gate ./2024-01-decent

# M4: find a concrete path (Seer) and confirm it through the gate:
python -m verification_agent findpath --model 2024-01-decent.model.json --repo ./2024-01-decent --connect-gate

# M4.5: synthesize a gate scenario from a lead and run it through the unchanged gate:
python -m verification_agent synthesize --demo --workspace ./synth_ws --json examples/m45_synthesis.json

# M6: run the blind backtest and print the FROZEN three-tier scorecard:
python -m verification_agent backtest --decent-repo ./2024-01-decent --json examples/m6_backtest.json
```

The output is self-describing: a `tool_status` block records which external
tools actually ran, so a model built without Slither is clearly labeled
**degraded** and never mistaken for ground truth.

### Worked example

[`examples/2024-01-decent.model.json`](examples/2024-01-decent.model.json) is the
real M0 output for the settled Code4rena **Decent** contest (a cross-chain
protocol). From 132 entry points across 20 in-scope contracts, the specialization
filter surfaces 10 priority functions — including `UTBFeeCollector.collectFees`
(an `ecrecover`-based fee-signature path) and the cross-chain `UTB.bridgeAndExecute`
/ `DecentEthRouter.bridge` entrypoints — each with the keyword evidence that
flagged it.

## The verification surface (the specialization)

The tagger ([`verification_agent/model/surface.py`](verification_agent/model/surface.py))
classifies functions into five priority categories. It is recall-biased: a
missed surface is far more expensive than an over-tagged one, and every tag
carries its evidence for human review.

| Category | Examples it catches |
|---|---|
| `signature_proof_verification` | `ecrecover`, EIP-1271 `isValidSignature`, ECDSA/BLS/pairing, `verifyProof`, groth16/plonk |
| `merkle_state_proof` | merkle/inclusion proofs, state/storage/account proofs, RLP/MPT/trie, checkpoint roots |
| `bridge_inbound_handler` | `relayMessage`, `lzReceive`, `ccipReceive`, `handle`, withdrawal proving/claiming |
| `cross_domain_auth` | `xDomainMessageSender`, `crossDomainMessenger`, trusted-remote / peer / endpoint checks |
| `slashing_avs_state` | slashing/freeze/jail, EigenLayer/AVS operator-set & stake-registry transitions |

## Architecture

```
INGEST → MODEL → [ HYPOTHESIZE → FIND-PATH → VERIFY → TRIAGE → REPORT ] → LEARN
                 └────────────── iterate until time budget / coverage ──────┘
```

```
verification_agent/
  ingest/   clone.py, build.py        — clone @ commit, detect+run Foundry/Hardhat
  model/    slither_runner.py         — Slither -> structural model (primary path)
            lite.py                   — regex fallback (degraded, clearly labeled)
            surface.py                — the specialization filter
            model_builder.py          — stitches the TargetModel together
  verify/   VerifyGate.sol            — on-chain 4-phase truth gate (M1)
            DecentFeeBypass.t.sol     — scenario + 5 cases (known-true/false/wrong-reason/2x malformed)
            harness.py                — install templates, run forge, parse verdict
            gate.py, case.py, cases.py — verdict taxonomy + M1 case registry
  kb/       store.py, schema.py       — mechanism-feature retriever; prior-only (M2)
            embedder.py               — lexical tiebreaker behind a pluggable Embedder
            query.py, data/*.jsonl    — query builders + curated dual-source corpus
  hypothesize/ engine.py, ev.py       — M0 surface + M2 priors → EV-ranked candidates (M3)
            invariants.py             — invariant pattern library (the predicate)
            provider.py               — offline + Claude generators; no gate import
  pathfind/ seer.py                   — structural reachability engine (M4)
            medusa.py, halmos.py      — fuzz + symbolic adapters; solidity/ harness
            orchestrator.py           — backend dispatch + coverage map; no gate import
  synthesize/ templates.py            — target-agnostic scenario template; faithful + rigged (M4.5)
            synthesizer.py            — lead → scenario; enforces the honest boundaries
            deploygraph.py            — derive collaborator deploy+wiring from the M0 model
            signature.py              — detect signing scheme + construct the Control signature
            runner.py                 — runs the synthesized scenario through the real gate
  backtest/ tiers.py                  — FROZEN three-tier taxonomy; a lead is not a catch (M6)
            contests.py               — lane-curated registry + answer keys (scorer-only)
            runner.py                 — BlindRunner: runs the loop on code alone, never reads keys
            scorer.py                 — opens keys post-freeze; mechanical tier assignment
  schema.py                           — the JSON contract every stage consumes
  cli.py                              — model/verify/kb/hypothesize/findpath/synthesize/backtest (M0–M6)
fixtures/   SurfaceSampler.sol        — offline fixture for the tagger
tools/      build_corpus.py           — regenerates the curated KB corpus
            validate_recall.py        — M0 recall vs the judged Decent finding set
docs/       M0_recall / M1_verify_gate / M2_knowledge_base / M3_hypothesis_engine / M4_path_backends / M4.5_scenario_synthesis / M6_backtest
tests/      test_surface / test_verify_gate / test_kb / test_hypothesize / test_pathfind / test_synthesize / test_deploygraph / test_signature / test_backtest — offline
```

## Hard constraints

1. **Verify-or-discard** — no finding without a fork-executed, reproducing PoC.
2. **Fork / testnet only** — never against live mainnet value; authorized
   contest/bounty scope only; no live-exploitation or "rescue" paths.
3. **Human-in-the-loop** — the agent surfaces ranked verified findings; the
   operator judges and submits. No auto-submission.
4. **Specialization discipline** — prioritize the verification/reachability/
   cross-chain surface; don't drift into saturated generic DeFi scanning.
5. **Honest state labels** on every module: IMPLEMENTED / PARTIAL / PROPOSED /
   SPECULATIVE.
