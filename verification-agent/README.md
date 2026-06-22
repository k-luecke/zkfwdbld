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

Nothing upstream of the harness (hypotheses, path-finding, the verify gate)
exists yet — by design. The build order is load-bearing.

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
  schema.py                           — the JSON contract every stage consumes
  cli.py                              — `model` command (M0)
fixtures/   SurfaceSampler.sol        — offline fixture for the tagger
tests/      test_surface.py           — offline tests (no network/forge/slither)
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
