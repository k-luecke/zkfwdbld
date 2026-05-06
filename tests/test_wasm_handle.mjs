// tests/test_wasm_handle.mjs — End-to-end Wasm `handle` smoke test.
//
// Audit I-7 (#42): the previous integrated test file (`tests/test_seer_eval.mjs`)
// covered only the Node-side `seer_eval/` modules. The Wasm `handle` ABI was
// only exercised inside Step 5 of `cutover.mjs`, which is hard to run on demand
// because it is wrapped inside a 7-step deploy pipeline.
//
// This file extracts that smoke test so it can be run in isolation:
//
//   node tests/test_wasm_handle.mjs                # auto-skip if seer.wasm is absent
//   node tests/test_wasm_handle.mjs path/to.wasm   # explicit path
//
// Behaviour:
//   - Skips with exit 0 when seer.wasm is missing (fresh clone, CI without
//     a prior build_wasm.sh) so the test is safe to run in default `npm test`.
//   - When the artifact is present, instantiates it and calls handle() with the
//     same SMOKE_FIXTURE that cutover.mjs uses. Asserts satisfiable=true.
//
// To force-fail on a missing artifact set SEER_REQUIRE_WASM=1.

import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Buffer } from 'node:buffer';

// SMOKE_FIXTURE must stay byte-identical with the same constant in
// cutover.mjs so the smoke step there and this standalone test exercise the
// same handle() input. cutover.mjs imports heavy AO/Turbo SDKs at module
// load time, so we duplicate the fixture here rather than import it.
const SMOKE_FIXTURE = Object.freeze({
  Action: 'Prove',
  cnf: [[1, 2, -3], [-1, 2, 3]],
  num_vars: 3,
  seed: 42,
});

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');

const WASM_PATH = process.argv[2]
  ? path.resolve(REPO_ROOT, process.argv[2])
  : path.join(REPO_ROOT, 'seer.wasm');

if (!existsSync(WASM_PATH)) {
  if (process.env.SEER_REQUIRE_WASM === '1') {
    console.error(`test_wasm_handle: seer.wasm not found at ${WASM_PATH}`);
    process.exit(1);
  }
  console.log(`test_wasm_handle: SKIP (no wasm artifact at ${WASM_PATH})`);
  process.exit(0);
}

const wasmBytes = readFileSync(WASM_PATH);
const { instance } = await WebAssembly.instantiate(wasmBytes);
const { memory, alloc, dealloc, handle } = instance.exports;

const inputBytes = Buffer.from(JSON.stringify(SMOKE_FIXTURE), 'utf-8');
const ptr = alloc(inputBytes.length);
if (!ptr) {
  console.error('test_wasm_handle: alloc() returned null');
  process.exit(1);
}
new Uint8Array(memory.buffer, ptr, inputBytes.length).set(inputBytes);

const packed = handle(ptr, inputBytes.length);
// dealloc(ptr, …) NOT called here — handle() already consumed/freed the input
// buffer, per the documented memory contract in src/lib.rs.

const respPtr = Number(BigInt(packed) >> 32n) >>> 0;
const respLen = Number(BigInt(packed) & 0xFFFF_FFFFn);
if (!respPtr) {
  console.error('test_wasm_handle: handle() returned null response pointer');
  process.exit(1);
}

const respBytes = new Uint8Array(memory.buffer, respPtr, respLen);
let response;
try { response = JSON.parse(Buffer.from(respBytes).toString('utf-8')); }
finally { dealloc(respPtr, respLen); }

if (!response.success) {
  console.error(`test_wasm_handle: response.success=false, error=${response.error}`);
  process.exit(1);
}
if (response.satisfiable !== true) {
  console.error(`test_wasm_handle: expected satisfiable=true, got ${response.satisfiable}`);
  process.exit(1);
}
if (!response.witness?.length) {
  console.error('test_wasm_handle: missing witness bytes in response');
  process.exit(1);
}

console.log(
  `test_wasm_handle: OK — handle() returned satisfiable=true, ` +
    `witness=${response.witness.length} bytes`
);
