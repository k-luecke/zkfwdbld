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
  exact evidence that triggered each tag so a human can audit the heuristic.

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

Hypothesis generation and path-finding (which will *produce* the PoCs the gate
rules on) do not exist yet — by design. The build order is load-bearing: the
gate is trusted before anything upstream of it is built.

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
  schema.py                           — the JSON contract every stage consumes
  cli.py                              — `model` (M0), `verify` (M1), `kb` (M2) commands
fixtures/   SurfaceSampler.sol        — offline fixture for the tagger
tools/      build_corpus.py           — regenerates the curated KB corpus
docs/       M1_verify_gate.md, M2_knowledge_base.md — design + soundness docs
tests/      test_surface.py, test_verify_gate.py, test_kb.py — offline tests (no network/forge)
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
