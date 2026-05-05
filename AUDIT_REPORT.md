# zkfwdbld Code Audit Report

Date: 2026-05-05
Repo: `/home/user/zkfwdbld`
Scope: Rust prover core, Tauri desktop shell, Node.js seer_eval pipeline,
Python heuristics, AO Lua agent, deployment scripts, ops policy layer.
Excluded: large `Heuristics/*.ipynb` notebooks (per request), `package-lock.json`.

---

## Executive Summary

`zkfwdbld` is a research-stage prototype built around a Goldilocks-field R1CS
prover for 3-SAT, wired through several non-overlapping consumer surfaces (an
AO/HyperBEAM agent, a Node "trust layer" pipeline, a Tauri viewer). The Rust
prover core is the strongest part of the system: the constraint set (with
the explicit `s_j = 1` enforcement row added) is correct for what it claims,
and the test suite covers the obvious soundness traps (zero literals, lying
satisfaction wires, corrupted intermediate `t_j`, non-Boolean inputs,
length mismatches, oversized inputs). The Wasm ABI is small but contains
one real correctness bug around `dealloc` on the host-supplied input pointer.

The much bigger problem is the **gap between what the prover proves and
what the rest of the system claims it proves**. The Lua orchestrator
(`agent.lua`) and every Node "claim encoder" (`seer_eval/claim_encoder.mjs`)
emit a fixed, content-free CNF (`[[1,1,1],[2,2,2],[3,3,3]]` or
`[[1,2,-3],[-1,2,3],[1,-2,3]]`) regardless of the `fact` / `context` /
`finding` provided. The proof is therefore independent of the data being
"proved", yet downstream code labels artifacts `verified` and produces
"engineering handoff" reports that say findings are ready for engineering
to act on. `docs/proof_contract.md` correctly identifies this as a demo
boundary, but neither `agent.lua`'s "Causation-Proof" emission path nor
`scanner_pipeline.mjs` / `harness_pipeline.mjs`'s "verified" trust state
respect that boundary in code — only `agent.lua` partially gates it via a
`DEMO_PROOF_MODE` flag, which downgrades the action tag but not the
"satisfiable=true" semantics.

Security-wise: no credentials are committed, but `deploy.js` hardcodes a
specific user's home path (`/home/kyle_w_luecke/.aos.json`). The Tauri
capabilities file exposes `core:default` (broad) with no narrowing for an
app whose static frontend builds DOM via `innerHTML` from JSON-derived
markdown — a concrete XSS surface if the snapshot ever contains attacker
data. `prover_bridge.mjs` shells out to `cargo run` and to
`wsl.exe bash -lc` with a path injected via single-quoted interpolation,
which is unsafe under unusual `cwd`. `harness/serve_harness.mjs` uses a
naive `..` strip that does not actually prevent path traversal.

Sprawl is severe: there are six near-duplicate spawn scripts
(`deploy.js`, `deploy_seer.js`, `deploy_paxiom.js`, `spawn_seer.js`,
`hb_spawn.js`, `hb_spawn.mjs`, `hb_spawn_direct.mjs`, `direct_spawn.js`,
`debug_spawn.js`, plus `cutover.mjs` which subsumes most of them) with
slightly different module TXs, schedulers, signers, and HTTP endpoints —
no shared library, no obvious authoritative path. Several Python files
under repo root (`goldilocks.py`, `monitor_vitals.py`,
`projection_benchmarks.py`, `simulate_memory.py`, `time_to_proof.py`)
are scratch/REPL scripts unrelated to the build.

Total findings: **44** (3 Critical, 7 High, 14 Medium, 11 Low, 9 Info).

---

## Findings by Severity

### Critical

| # | ID | File:Line | Title |
|---|----|-----------|-------|
| 1 | C-1 | `agent.lua:138-151` and `seer_eval/claim_encoder.mjs:64-86` | Claim encoders emit fixed CNF independent of `fact`/`finding`; proof carries zero binding to the data |
| 2 | C-2 | `seer_eval/scanner_pipeline.mjs:25-58`, `harness_pipeline.mjs:82-128` | Pipeline labels artifacts `trust_state: 'verified'` and `demo_only: false` despite using the unbinding demo encoder above |
| 3 | C-3 | `src/lib.rs:269-289` (`handle`) | `handle()` does not free the host-supplied input buffer it receives; the contract docstring says only the response must be freed, but combined with C-4 below this is the more serious half — repeated calls leak linear memory the host expects to own |

### High

| # | ID | File:Line | Title |
|---|----|-----------|-------|
| 4 | H-1 | `agent.lua:228-256` (`Proof-Result` handler) | Demo-mode results are downgraded to `Demo-Proof-Result` but still propagate `satisfiable=true` and the prover witness; downstream consumers gated only on the action string can be tricked into trusting a demo |
| 5 | H-2 | `seer_eval/prover_bridge.mjs:42-44` | `wsl.exe bash -lc "cd '${wslCwd}' && cargo run …"` performs unescaped single-quoted interpolation of `process.cwd()`; a directory containing `'` (or `;`, `$`) yields shell injection |
| 6 | H-3 | `harness/serve_harness.mjs:24-28` | Path traversal protection is `req.url.split('?')[0].replace(/\.\./g, '')` then `path.join(__dirname, relPath)`. URL-encoded `%2e%2e` is not normalized and the strip leaves behind `'.../etc/passwd'` patterns; relies on `path.join` collapse only |
| 7 | H-4 | `src-tauri/capabilities/default.json:6` | Capability set is `["core:default"]` — Tauri's broad default surface — for an app whose web layer renders untrusted markdown into innerHTML; no narrow list, no CSP, no asset isolation |
| 8 | H-5 | `app/static/app.js:43-134, 207, 261` | Markdown renderer escapes content but inserts the resulting HTML via `innerHTML`; combined with the artifact's `summary`, `claim.title`, `evidence.snippet`, etc. being attacker-controllable in the scanner adapter, an XSS surface exists if the packet ever ingests unsanitized 3rd-party data. `escapeHtml` does not escape `"` or `'`, so any future attribute interpolation is unsafe |
| 9 | H-6 | `src/lib.rs:147` | `bytes_to_witness` calls `F::from(u64::from_le_bytes(arr))` — this accepts any `u64`, including values ≥ Goldilocks `p` (`0xFFFFFFFF00000001`), which silently wrap. A witness whose serialized bytes encode `p..2^64-1` is treated as the canonical residue, so witnesses are not unique and a verifier-side equality check on serialized bytes (which downstream tooling may add) would not match what `verify` accepts |
| 10 | H-7 | `agent.lua:73` (`scan_dom`) | Pattern matcher only finds the **first** match per pattern (`string.find` not `gmatch`); a page with multiple hidden inputs / comments / scripts only emits one finding per family. The Node `harness_pipeline.mjs:30` regex uses `matchAll` and finds all — the Lua scanner and the Node scanner therefore diverge in semantics for the same input |

### Medium

| # | ID | File:Line | Title |
|---|----|-----------|-------|
| 11 | M-1 | `deploy.js:12` | Hardcoded absolute path `/home/kyle_w_luecke/.aos.json` instead of `process.env.HOME`; reveals the developer's username and breaks for any other operator |
| 12 | M-2 | `agent.lua:20-23` | `MODULE_ID` and `PROVER_PID` defaults are real, anchored process/module IDs baked into source. If these are stale/misconfigured the agent will silently route to a wrong process; there is no liveness/identity check on first use |
| 13 | M-3 | `agent.lua:283`, `agent.lua:317` | `Set-Prover` and `Flush-Buffer` only check `msg.From == ao.env.Process.Owner` — single owner key compromise (or any AOS process where Owner is the wallet that paid the spawn fee) trivially redirects all outbound proof requests to an attacker-controlled `PROVER_PID` |
| 14 | M-4 | `seer_eval/message_policy.mjs:73` | `body.includes(policy.required_disclosure)` — case sensitive and substring-only; "sent by ai assistant" or "Sent by AI Assistant " (trailing space) misses; conversely, an HTML-escaped or whitespace-broken disclosure may be matched accidentally |
| 15 | M-5 | `seer_eval/message_policy.mjs:54-62` | `approved_families` short-circuits BEFORE recipient/blocked-recipient/disclosure checks — a request with an unsupported family returns `unsupported_policy` and never logs any of the other policy violations the operator might want to see (silent loss of triage data) |
| 16 | M-6 | `seer_eval/message_policy.mjs:43` | `disallowed_phrases` does word-substring matching: `'guarantee'` in `policy` would block legitimate text containing the word "guarantees" or "guaranteed performance"; conversely, `g​uarantee` (zero-width) bypasses |
| 17 | M-7 | `ops/policies/outbound_message_policy.json` | `blocked_recipients: []` and `required_subject_prefix: ""` mean the default policy is an allowlist for any recipient at `customer.example`/`prospect.example` with arbitrary subject; demo-grade defaults shipping in `ops/` may be assumed by an operator to be production-ready |
| 18 | M-8 | `seer_eval/prover_bridge.mjs:22-27` | `spawnSync('cargo', …)` with no per-call timeout and no max-buffer cap; a hung Rust build (e.g. dependency download) blocks the Node pipeline indefinitely, and a chatty proof can blow the default 1 MiB stdout buffer |
| 19 | M-9 | `seer_eval/ops_runner.mjs:25-40` | `runOutboundMessageOpsLoop` reads the queue twice (`loadOpsQueue` then `reviewedArtifactsFromDraftFile` reads the same file), with no atomicity. A queue file rewritten between the two reads yields an `action_count` that disagrees with the bundle |
| 20 | M-10 | `cutover.mjs:255-268` | `patchAgentLua` uses a regex-replace on the Lua source. If the regex `/PROVER_PID\s*=\s*PROVER_PID\s+or\s+"[^"]+"/` doesn't match (e.g., user reformatted, added a comment), the function `die`s — but the upstream new module spawn has already happened and is logged. The repo can be left in an inconsistent state with a new live module and an unpatched agent |
| 21 | M-11 | `src/lib.rs:225-249` | `alloc(0)` returns 0; `dealloc` of `(0, _)` or `(_, 0)` is a no-op. Combined, this pattern means an attacker can probe whether a particular `(ptr, size)` pair was previously allocated by the host (`dealloc` succeeds quietly even on aliasing). Not exploitable in the AO model but hostile to debugging |
| 22 | M-12 | `src/r1cs.rs:301` | `debug_assert_eq!(row, n + 4 * m + 1, "row count mismatch")` — `debug_assert!` is compiled out under `--release` (which is exactly how the Wasm is built per `Cargo.toml:18-22`); a future builder change that mis-counts rows would silently produce a malformed R1CS in production |
| 23 | M-13 | `src/witness_gen.rs:130` | `MAX_VARS = 26` is enforced in `lib.rs::validate_cnf` (good), but `generate_witness` independently hard-codes 26 (`witness_gen.rs:130`). Two sources of truth — easy to drift |
| 24 | M-14 | `seer_eval/score.mjs:44-46` | `OUTCOME_BASE[outcomeKey] ?? 0` — any unknown `outcome` value (typo, schema drift) silently scores 0. No error/warning. The same fallback is used in the breakdown's `outcome.raw`, so the run looks like a legitimate FAIL rather than a malformed input |

### Low

| # | ID | File:Line | Title |
|---|----|-----------|-------|
| 25 | L-1 | `src/witness_gen.rs:101` | `rng.r#gen::<f64>()` produces a uniform `[0,1)` f64 then Gaussian-smooths it. Comment in `validation_script.py:11` says "random.gauss(0, 1)" — the Python heuristic and the Rust witness use **different distributions** for the symbolic field. Python `validation_script.py` writes `Heuristics/site_config.json` with Gaussian samples that the Rust kernel never consumes |
| 26 | L-2 | `src/witness_gen.rs:59-87` (`gaussian_smooth_1d`) | Reflect padding uses `j = -j - 1` and `j = 2*n - j - 1`. For `n == 1` and large kernel, the `(j as usize).min(n - 1)` clamp is needed; if `n == 0` the function would panic. The caller protects against `n == 0` upstream, but the helper is `pub(crate)` and could be called elsewhere |
| 27 | L-3 | `src/lib.rs:127-134` | `witness_to_bytes` uses `f.into_bigint().0[0]` (single u64 limb). This is correct for Goldilocks's single-limb Mont backend, but if `MontBackend<_, N>` ever becomes `N>1` the silent truncation produces invalid witnesses. No assertion catches this |
| 28 | L-4 | `seer_eval/claim_encoder.mjs:14-21` | `hashSeed` is a 32-bit FNV-1a; `>>> 0` then passed as the field-coefficient seed. 32 bits of entropy is fine for a demo, but the Rust `seed: Option<u64>` field accepts 64. Half the field-coefficient space is unused |
| 29 | L-5 | `seer_eval/audit.mjs:80` | `appendFileSync` is "atomic at OS syscall level" only for writes < `PIPE_BUF` (typically 4 KB on Linux). Records can exceed that easily once metrics grow; concurrent writers would interleave |
| 30 | L-6 | `seer_eval/registry.mjs:19-25` | `loadJson` swallows all parse errors and returns `null` ⇒ empty registry. A corrupted registry file silently degrades scoring (adaptation tier always 0) with no warning logged |
| 31 | L-7 | `app/server.mjs:35-65` | `existsSync` race vs `createReadStream`; if file is deleted between the two, `pipe(res)` errors after status 200 is sent. Minor (local-only server) |
| 32 | L-8 | `consolidate_baselines.mjs:81-86` | Silently drops malformed JSONL lines via `try { return [JSON.parse(line)]; } catch { return []; }`. No counter is exposed for "lines skipped"; corrupted run logs degrade baselines invisibly |
| 33 | L-9 | `src/lib.rs:34-46`, `r1cs.rs:148`, `agent.lua:148` | The `cnf` field accepts `Vec<Vec<i32>>` of arbitrary inner length; `validate_cnf` enforces exactly 3, but several callers (`agent.lua:148`) hard-code 3-literal clauses. The "3-SAT only" constraint is not in the type — a refactor that allows k-SAT would silently break R1CS row indexing in `r1cs.rs::build_sat_constraints` (which assumes `clause[0..2]`) |
| 34 | L-10 | `src-tauri/tauri.conf.json:7-15` | `beforeBuildCommand` and `beforeDevCommand` execute `node app/generate_packet_json.mjs` unconditionally; if `artifacts/polsia-demo-packet/` is missing the build dies, breaking offline development. The script is also silently overwriting `app/static/generated/packet.json` (in `.gitignore`, so it works but is undocumented) |
| 35 | L-11 | `Cargo.toml:4` | `edition = "2024"` is set; this requires very recent stable Rust. No `rust-version` floor is declared, so a contributor with stable < 1.85 will see opaque errors |

### Info

| # | ID | File:Line | Title |
|---|----|-----------|-------|
| 36 | I-1 | `agent.lua:113-167` | "Stub" CNF marker comment correctly identifies the encoder gap, but no enforcement: nothing prevents `DEMO_PROOF_MODE` being unset while still using the stub CNF path |
| 37 | I-2 | `cutover.mjs:38-39, 224-225` | Hardcoded `TOTAL_STEPS = 8` and a hardcoded sample CNF in the WASM smoke test; if the kernel input shape changes, the smoke step's "success" doesn't actually exercise the real prover input the orchestrator uses |
| 38 | I-3 | `seer_eval/score.mjs:11` | Composite weights `{outcome:0.40, efficiency:0.25, discipline:0.25, adaptation:0.10}` not asserted to sum to 1.0; a future edit that breaks this is not caught |
| 39 | I-4 | `seer_eval/classify.mjs:90-91` | `conflictThreshold` and `activationThreshold` defaults (`0.10`, `0.30`) are policy decisions baked into code, not config. Hard to audit whether classification behavior is intentional after a model swap |
| 40 | I-5 | `Heuristics/site_config.json` | Static, hand-written `symbolic_field` of length 100 and `seed: 42` is committed; nothing in the live Rust path consumes this file. It's effectively dead config |
| 41 | I-6 | `goldilocks.py`, `simulate_memory.py`, `monitor_vitals.py`, `projection_benchmarks.py`, `time_to_proof.py` | Five Python REPL/sketch files at repo root with no entry point in any pipeline, no tests, no docs reference. Should be moved under `experiments/` or removed |
| 42 | I-7 | `tests/test_seer_eval.mjs` | Single integrated test file (~800 lines, ~70 tests). All covered functionality is for `seer_eval/`; no JS test exercises `prover_bridge.mjs`, `cutover.mjs`, deploy/spawn scripts, or the Tauri/static viewer JS. No `cargo test` integration test that exercises the full Wasm `handle` ABI |
| 43 | I-8 | `package.json:9-13` | Three runtime deps pinned to exact versions (`1.41.0`, `1.0.3`, `0.0.94`) — good for reproducibility, but no `npm audit` / lockfile-only-install workflow (`npm ci`) documented |
| 44 | I-9 | `examples/prover_scaling.rs:8-29` | XorShift64 reseeds with `seed.max(1)` to avoid zero-state, but the surrounding test uses `seed=42` only — there is one data point per `(num_vars, num_clauses)`. Reported timings have no variance/CI estimate |

---

## Architecture Overview

### Layer 1 — Rust prover core (`src/`, `Cargo.toml`, `build_wasm.sh`)

- `src/fields.rs`: Goldilocks field (`p = 2^64 - 2^32 + 1`) via `ark-ff` Mont
  backend, fixed-point f64 → field encoder (`SCORE_SCALE = 2^32`). Single-limb.
- `src/r1cs.rs`: 3-SAT → R1CS builder. Wire layout
  `[1, b_0..b_{n-1}, s_0..s_{m-1}, score, t_0..t_{m-1}]`, total `n + 2m + 2`
  wires, `n + 4m + 1` constraints. Includes the explicit `s_j · 1 = 1`
  satisfaction row that closes the soundness gap of an earlier version, plus
  a score row that binds `curvature_score` to `Σ coeff_i·b_i + offset`.
- `src/witness_gen.rs`: exhaustive `2^n` search (≤ 26 vars) over
  Gaussian-smoothed symbolic/entropy fields, picks the satisfying assignment
  that maximizes the curvature-weighted score.
- `src/lib.rs`: JSON dispatch (`Action: "Prove" | "Verify"`), Wasm linear-memory
  ABI (`alloc`/`dealloc`/`handle`), input validation (`MAX_VARS=26`,
  `MAX_CLAUSES=4096`, `MAX_INPUT_BYTES=1 MiB`).
- Build: `build_wasm.sh` → `wasm32-unknown-unknown` release with
  `lto=true, opt-level=z, panic=abort`; optional `wasm-strip`.

### Layer 2 — AO/HyperBEAM agent (`agent.lua`, deploy scripts, `cutover.mjs`)

- `agent.lua`: an AOS process with handlers
  `Scan-Page`, `Proof-Result`, `Flush-Buffer`, `Set-Prover`, `Buffer-Status`.
  Buffers up to 1 000 findings, dispatches to the anchored Seer prover
  process by PID, tracks pending proofs by `Correlation-Id`. Emits a
  fixed sample CNF (`DEMO_PROOF_MODE`) regardless of finding content.
- Deploy scripts: at least 9 near-duplicate `.js`/`.mjs` files for spawning
  the prover module — see Sprawl section.
- `cutover.mjs`: the most-complete operational script — uploads new wasm
  via Turbo SDK, waits for Arweave indexing, spawns via HyperBEAM `/push`,
  verifies module binding, runs an in-process WebAssembly smoke test,
  patches `agent.lua` atomically, and logs to `cutover.log`.

### Layer 3 — Node "trust layer" pipeline (`seer_eval/`, `examples/`, `app/`)

- Adapters (`adapters.mjs`) normalize three input kinds — synthetic harness
  findings, mocked scanner exports, agent outputs — and outbound message
  drafts into a single canonical `verified_finding` / `agent_action`
  artifact shape (`finding_artifact.mjs`).
- Pipelines (`harness_pipeline.mjs`, `scanner_pipeline.mjs`,
  `message_pipeline.mjs`) call the adapters, then optionally call the
  Rust prove/verify path via `prover_bridge.mjs` (which `spawnSync`s
  `cargo run --example prove_request`).
- `claim_encoder.mjs` is the only "encoder"; it maps a hidden-input
  finding to a fixed CNF and a hash-derived seed. The CNF is data-independent.
- `message_policy.mjs` is a pure JS bounded-policy gate (allowlists,
  disallowed phrases, max body length) — produces `ready_to_send` /
  `needs_review` / `unsupported_policy` states.
- Reporting: `report_renderer.mjs` produces markdown,
  `report_exporter.mjs` writes per-finding bundles, `demo_packet.mjs`
  builds an `overview.md` + `talk_track.md` packet.
- `score.mjs`, `classify.mjs`, `audit.mjs`, `registry.mjs`,
  `consolidate_baselines.mjs`: a separate, parallel scoring system based
  on a 4-tier composite (outcome, efficiency, discipline, adaptation)
  driven by `seer_runs.jsonl`. **This scoring layer is not connected to
  the prover/artifact pipeline** — it appears to be aspirational machinery
  for evaluating future agent runs.

### Layer 4 — Tauri desktop shell (`src-tauri/`, `app/`)

- A thin Tauri 2 wrapper around an HTML/JS viewer. The build runs
  `node app/generate_packet_json.mjs` to produce a JSON snapshot
  consumed by `app/static/app.js`. The viewer renders markdown into
  the DOM via a hand-rolled renderer + `innerHTML`. Capability set is
  `core:default` — wide-open Tauri APIs.

### Layer 5 — Python heuristics (`Heuristics/`, repo-root `*.py`)

- `Heuristics/`: a handful of Jupyter notebooks (skipped per request),
  `site_config.json` (a 100-var symbolic field; not consumed by the Rust
  kernel), `test_vector_1.cnf` (DIMACS 3-SAT, 100 vars / 400 clauses),
  `micro24_nocap.pdf`. None of these feed the live pipeline.
- Repo-root Python: `goldilocks.py` (REPL), `monitor_vitals.py` (psutil),
  `projection_benchmarks.py`, `simulate_memory.py`, `time_to_proof.py`,
  `validation_script.py`, `generate_sat.py`. These are scratch/sketch
  files, not part of any pipeline.

### Cross-layer flow (intended)

```
External crawler → AO Scan-Page → agent.lua scan_dom → fcc_dispatch
       → Seer Wasm process (handle → dispatch → R1CS verify)
       → Proof-Result → originating crawler
```

The Node `seer_eval` pipeline is a **separate, parallel** flow that
re-implements scanning (`scanHarnessHtml`), encoding
(`encodeHiddenInputClaim`), and proving (via `cargo run`), bypassing
the AO agent entirely. The two paths share only the Rust prover crate.

---

## Script Sprawl Problem

There are **nine** spawn/deploy scripts that all do the same thing
(load `~/.aos.json`, spawn an AO process bound to the Seer module),
diverging only in:

| Script | API | Endpoint | Module TX | Scheduler | Live? |
|---|---|---|---|---|---|
| `deploy.js` | aoconnect `spawn` | (default MU) | `ghSkge2sIUD…` | `_GQbaH9vunE…` | uses hardcoded path |
| `deploy_seer.js` | aoconnect `spawn` | (default MU) | `SBNpk70S…` | `_GQbaH9vunE…` | yes |
| `deploy_paxiom.js` | Turbo + `connect/createSigner` | (default MU) | dynamic (uploads) | `_GQbaH9vunE…` | yes |
| `spawn_seer.js` | aoconnect 0.0.93 `connect`/`createSigner` | (default MU) | `j_yTLMEoAs2m…` | `TZ7o7SIZ06…` | yes |
| `hb_spawn.js` | `connect({MODE:'mainnet', URL})` | `tee-6.forward.computer` | `j_yTLMEoAs2m…` | `n_XZJhUnmldNF…` | yes |
| `hb_spawn.mjs` | same, ESM | `hyperbeam.permaweb.black:10000` | `j_yTLMEoAs2m…` | `ZqkuoHZ3GTSC…` | yes |
| `hb_spawn_direct.mjs` | bypass aoconnect, `arbundles` | `push.forward.computer` | `j_yTLMEoAs2m…` | dynamic (meta) | yes |
| `direct_spawn.js` | bypass aoconnect, `arbundles` | `ao-mu-1.onrender.com` | `j_yTLMEoAs2m…` | `TZ7o7SIZ06…` | yes |
| `debug_spawn.js` | aoconnect, fetch interceptor | `mu.ao-testnet.xyz` | `j_yTLMEoAs2m…` | `_GQ33BkPtZrqx…` | yes |
| `cutover.mjs` | `arbundles` + Turbo + HB | `push.forward.computer` | dynamic (uploads) | dynamic (meta) | yes |

Each carries:
- its own `MODULE_TX` string literal (4 different values across files)
- its own `SCHEDULER` (5 different values)
- its own retry/backoff (2-of-9 have backoff; rest are one-shot)
- its own wallet-load incantation (3 different patterns)
- its own crypto polyfill (`if (typeof crypto === 'undefined')`) duplicated 5 times

**Recommendation:**

1. Delete `deploy.js`, `deploy_seer.js`, `direct_spawn.js`, `debug_spawn.js`,
   `hb_spawn.js`. They are partial drafts superseded by `cutover.mjs`.
2. Extract a `lib/aoSpawn.mjs` module exposing `spawnSeer({ moduleTx,
   scheduler, endpoint, signer, retries })`. Have `cutover.mjs` and one
   `spawn.mjs` (combining `spawn_seer.js` + `hb_spawn_direct.mjs`)
   import it.
3. Move all hardcoded `MODULE_TX` / `SCHEDULER` / `HB_URL` strings into
   a single `deploy/config.json` checked into the repo, so an operator
   can audit "what is this script actually pointing at" in one place.
4. Apply the same to the Python sketch files: move the seven repo-root
   `.py` files under `experiments/sketches/` and add `experiments/README.md`
   pointing to them.

---

## Notes on the Proof Contract

`docs/proof_contract.md` is correct in identifying the issue but is not
enforced by code. To bring the implementation in line with the contract:

- `agent.lua::fcc_dispatch` should refuse to send "Prove" requests when
  `DEMO_PROOF_MODE` is true unless the recipient is explicitly the demo
  inspector — currently it just retags the result on receipt.
- `seer_eval/claim_encoder.mjs` should, at minimum, derive the CNF from
  `finding.raw_string` (e.g., bit-encode the snippet hash into literal
  polarities) so the proof binds to the data even in demo mode.
- `seer_eval/scanner_pipeline.mjs` and `harness_pipeline.mjs` must not
  set `trust_state: 'verified'` and `demo_only: false` while consuming
  the demo encoder; either gate on a "real encoder available" flag, or
  introduce a third state (`liveness_verified`) that does not promise
  data binding.

---

## Suggested Triage Order

1. **C-1, C-2, H-1**: close the proof-binding gap before any external demo.
2. **H-2, H-3, H-4, H-5**: tighten the local attack surface; trivial fixes.
3. **C-3, H-6, M-11, M-12**: harden the Wasm ABI before the next module upload.
4. **M-3**: re-evaluate the agent-trust boundary (single-owner = full PID
   redirection).
5. Sprawl cleanup (script consolidation) — large diff, low risk, big
   maintainability win.
