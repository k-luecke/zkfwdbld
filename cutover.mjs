// cutover.mjs — Full Seer module redeploy + agent.lua hot-patch.
//
// Steps:
//   1. Upload new seer.wasm via Turbo → new module TX
//   2. Wait for module TX to appear on Arweave gateway
//   3. Spawn new Seer process via push.forward.computer
//   4. Verify PID Module tag == new TX (hard-fail on mismatch)
//   5. WASM local smoke test (invoke handle() in-process)
//   6. Patch PROVER_PID in agent.lua (atomic write via tmp file)
//   7. Sanity-read agent.lua to confirm PID is present
//   8. Append result to cutover.log and print reload instructions
//
// Usage: node cutover.mjs
// Safe to run before credits are available — aborts at balance check.

import { TurboFactory }    from '@ardrive/turbo-sdk';
import { ArweaveSigner, createData } from '@dha-team/arbundles/node';
import { DataItem }        from '@dha-team/arbundles';
import {
  readFileSync, createReadStream, statSync,
  writeFileSync, renameSync, appendFileSync,
} from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname  = path.dirname(fileURLToPath(import.meta.url));
const HOME       = process.env.HOME;
const HB_URL     = 'https://push.forward.computer';
const GW_BASE    = 'https://arweave.net';
const WASM_PATH  = path.join(__dirname, 'seer.wasm');
const AGENT_PATH = path.join(__dirname, 'agent.lua');
const LOG_PATH   = path.join(__dirname, 'cutover.log');
const ROLLBACK_PATH = path.join(__dirname, 'rollback-needed.json');

// Regex for the PROVER_PID assignment in agent.lua. Tolerates either single
// or double quotes around the default literal — keep this in sync between the
// pre-spawn assertion (Step 0) and the actual patch (Step 6).
const PROVER_PID_RE = /PROVER_PID\s*=\s*PROVER_PID\s+or\s+(['"])[^'"]*\1/;

const GW_POLL_MS    = 30_000;
const GW_TIMEOUT_MS = 10_000;
const GW_MAX_WAIT   = 10 * 60_000;
const PUSH_TIMEOUT  = 30_000;

// Audit I-2 (#37): derive the step count from the actual list of steps so a
// future re-shuffle can never drift from a hardcoded constant. Mirrored by
// the shared SMOKE_FIXTURE below.
export const STEPS = Object.freeze([
  'Upload seer.wasm via Turbo',
  'Wait for module TX on gateway',
  'Spawn new Seer process',
  'Verify PID Module tag',
  'WASM local smoke test',
  'Patch PROVER_PID in agent.lua',
  'Verify patch was written correctly',
  'Log result and print reload instructions',
]);
const TOTAL_STEPS   = STEPS.length;

// Audit I-2 (#37): the WASM smoke test fixture is exported so an out-of-band
// test (tests/test_wasm_handle.mjs) can exercise the same input and assert
// the smoke step would still pass. If the kernel input shape changes, both
// callers update in lockstep.
export const SMOKE_FIXTURE = Object.freeze({
  Action: 'Prove',
  cnf: [[1, 2, -3], [-1, 2, 3]],
  num_vars: 3,
  seed: 42,
});

// ── helpers ──────────────────────────────────────────────────────────────────

function fetchT(url, opts, ms) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  return fetch(url, { ...opts, signal: ctrl.signal }).finally(() => clearTimeout(t));
}

function step(n, msg) {
  console.log(`\n[${n}/${TOTAL_STEPS}] ${msg}`);
}

function die(msg) {
  console.error('\n✗ CUTOVER ABORTED:', msg);
  process.exit(1);
}

// ── Step 1: Upload wasm via Turbo ─────────────────────────────────────────────

async function upload(wallet) {
  step(1, 'Uploading seer.wasm via Turbo...');
  const size  = statSync(WASM_PATH).size;
  const turbo = TurboFactory.authenticated({ privateKey: wallet });

  const bal = await turbo.getBalance();
  console.log('  Turbo balance (winc):', bal.winc);
  if (BigInt(bal.winc) === 0n) die('Turbo balance is zero — top up before running cutover.');

  const result = await turbo.uploadFile({
    fileStreamFactory: () => createReadStream(WASM_PATH),
    fileSizeFactory:   () => size,
    dataItemOpts: {
      tags: [
        { name: 'Data-Protocol',   value: 'ao' },
        { name: 'Variant',         value: 'ao.TN.1' },
        { name: 'Type',            value: 'Module' },
        { name: 'Module-Format',   value: 'wasm32-unknown-unknown' },
        { name: 'Input-Encoding',  value: 'JSON-V1' },
        { name: 'Output-Encoding', value: 'JSON-V1' },
        { name: 'Content-Type',    value: 'application/wasm' },
        { name: 'Memory-Limit',    value: '500-mb' },
        { name: 'Compute-Limit',   value: '9000000000000' },
        { name: 'App-Name',        value: 'Paxiom-Seer' },
      ],
    },
  });

  const moduleId = result.id;
  console.log('  Module TX:', moduleId);
  return moduleId;
}

// ── Step 2: Wait for module TX on gateway ────────────────────────────────────

async function waitForModule(moduleId) {
  step(2, `Waiting for module TX ${moduleId} on gateway...`);
  const query = JSON.stringify({
    query: `{ transaction(id: "${moduleId}") { id tags { name value } } }`,
  });
  const deadline = Date.now() + GW_MAX_WAIT;

  for (;;) {
    if (Date.now() >= deadline) die(`Module TX not visible after ${GW_MAX_WAIT / 60000} min.`);
    try {
      const res  = await fetchT(`${GW_BASE}/graphql`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: query,
      }, GW_TIMEOUT_MS);
      const json = await res.json();
      const tx   = json?.data?.transaction;
      if (tx) {
        const tags = Object.fromEntries((tx.tags || []).map(t => [t.name, t.value]));
        console.log('  TX visible. Type:', tags['Type'], '| Format:', tags['Module-Format']);
        if (tags['Type'] !== 'Module') die('TX found but Type tag is not "Module".');
        return;
      }
    } catch { /* timeout or network — retry */ }
    console.log(`  Not indexed yet — waiting ${GW_POLL_MS / 1000}s...`);
    await new Promise(r => setTimeout(r, GW_POLL_MS));
  }
}

// ── Step 3: Spawn new Seer process ───────────────────────────────────────────

async function spawnSeer(wallet, moduleId) {
  step(3, 'Spawning new Seer process...');
  const signer = new ArweaveSigner(wallet);

  const metaRes = await fetchT(`${HB_URL}/~meta@1.0/info/address`, {}, 8_000)
    .catch(e => die(`Meta fetch failed: ${e.message}`));
  if (!metaRes.ok) die(`Meta fetch HTTP ${metaRes.status}`);
  const scheduler = (await metaRes.text()).trim();
  console.log('  Scheduler:', scheduler);

  const tags = [
    { name: 'device',           value: 'process@1.0'      },
    { name: 'scheduler-device', value: 'scheduler@1.0'    },
    { name: 'push-device',      value: 'push@1.0'         },
    { name: 'execution-device', value: 'genesis-wasm@1.0' },
    { name: 'Authority',        value: scheduler           },
    { name: 'Scheduler',        value: scheduler           },
    { name: 'Module',           value: moduleId            },
    { name: 'signing-format',   value: 'ans104'            },
    { name: 'accept-bundle',    value: 'true'              },
    { name: 'accept-codec',     value: 'httpsig@1.0'      },
    { name: 'App-Name',         value: 'Paxiom-Seer'      },
    { name: 'Entity-Type',      value: 'Seer-Agent'       },
    { name: 'Data-Protocol',    value: 'ao'               },
    { name: 'Type',             value: 'Process'           },
    { name: 'Variant',          value: 'ao.N.1'            },
  ];

  const dataItem = createData('1984', signer, { tags });
  await dataItem.sign(signer);
  const raw   = dataItem.getRaw();
  const valid = await DataItem.verify(raw);
  if (!valid) die('Data item failed local verification.');
  console.log('  Data item signed and verified. ID:', dataItem.id);

  for (let i = 1; i <= 4; i++) {
    let res;
    try {
      res = await fetchT(`${HB_URL}/push`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/ans104', 'codec-device': 'ans104@1.0' },
        body: raw,
      }, PUSH_TIMEOUT);
    } catch (e) {
      if (i < 4) { await new Promise(r => setTimeout(r, 2000 * (2 ** (i - 1)))); continue; }
      die(`Spawn POST failed after 4 attempts: ${e.message}`);
    }
    const pid = res.headers.get('process');
    if (pid) { console.log('  Seer PID:', pid); return pid; }
    if ([429, 500, 502, 503, 504].includes(res.status) && i < 4) {
      await new Promise(r => setTimeout(r, 2000 * (2 ** (i - 1)))); continue;
    }
    die(`Spawn failed — HTTP ${res.status}: ${await res.text().catch(() => '')}`);
  }
}

// ── Step 4: Verify PID Module tag (hard-fail on mismatch) ────────────────────

async function verifyBinding(pid, moduleId) {
  step(4, `Verifying PID ${pid} is bound to module ${moduleId}...`);
  const query = JSON.stringify({
    query: `{ transaction(id: "${pid}") { id tags { name value } } }`,
  });
  const deadline = Date.now() + GW_MAX_WAIT;

  for (;;) {
    if (Date.now() >= deadline) die('PID binding verification timed out — do not proceed without confirmation.');
    try {
      const res  = await fetchT(`${GW_BASE}/graphql`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: query,
      }, GW_TIMEOUT_MS);
      const json = await res.json();
      const tx   = json?.data?.transaction;
      if (tx) {
        const tags     = Object.fromEntries((tx.tags || []).map(t => [t.name, t.value]));
        const txModule = tags['Module'];
        if (txModule !== moduleId) {
          die(`Module tag mismatch: PID has "${txModule}", expected "${moduleId}". ` +
              'This spawn may be bound to a stale module. Aborting.');
        }
        console.log('  ✓ Module tag confirmed — PID is bound to the new module TX.');
        return;
      }
    } catch { /* retry */ }
    console.log(`  PID not indexed yet — waiting ${GW_POLL_MS / 1000}s...`);
    await new Promise(r => setTimeout(r, GW_POLL_MS));
  }
}

// ── Step 5: WASM local smoke test ────────────────────────────────────────────
// Instantiates seer.wasm in-process and invokes handle() with a known-good
// 3-variable SAT request.  Zero network dependency.
// Tests the exact artifact that was uploaded in step 1.

async function smokeTestWasm() {
  step(5, 'WASM local smoke test...');

  const wasmBytes = readFileSync(WASM_PATH);
  const { instance } = await WebAssembly.instantiate(wasmBytes);
  const { memory, alloc, dealloc, handle } = instance.exports;

  const input      = JSON.stringify(SMOKE_FIXTURE);
  const inputBytes = Buffer.from(input, 'utf-8');

  const ptr = alloc(inputBytes.length);
  if (!ptr) die('WASM alloc() returned null');
  new Uint8Array(memory.buffer, ptr, inputBytes.length).set(inputBytes);

  const packed  = handle(ptr, inputBytes.length);
  dealloc(ptr, inputBytes.length);

  const respPtr = Number(BigInt(packed) >> 32n) >>> 0;
  const respLen = Number(BigInt(packed) & 0xFFFF_FFFFn);
  if (!respPtr) die('WASM handle() returned null response pointer');

  const respBytes = new Uint8Array(memory.buffer, respPtr, respLen);
  let response;
  try { response = JSON.parse(Buffer.from(respBytes).toString('utf-8')); }
  finally { dealloc(respPtr, respLen); }

  if (!response.success)             die(`WASM smoke failed: ${response.error}`);
  if (response.satisfiable !== true) die(`Expected satisfiable=true, got ${response.satisfiable}`);
  if (!response.witness?.length)     die('Missing witness bytes in response');

  console.log('  ✓ handle() returned satisfiable=true');
  console.log(`    witness: ${response.witness.length} bytes (${response.witness.length / 8} field elements)`);
}

// ── Step 6: Patch PROVER_PID atomically ──────────────────────────────────────
// Write to a temp file, then rename into place.
// rename() is atomic on POSIX: a crash mid-write cannot produce a partial file.

function patchAgentLua(newPid, moduleId) {
  step(6, `Patching PROVER_PID in agent.lua → ${newPid}`);
  const src     = readFileSync(AGENT_PATH, 'utf-8');
  const patched = src.replace(
    PROVER_PID_RE,
    `PROVER_PID = PROVER_PID or "${newPid}"`
  );
  if (src === patched) {
    // Post-spawn failure: a new module + PID exist on-chain but agent.lua was
    // not updated. Emit a rollback marker so operators know what to clean up.
    const marker = {
      ts:        new Date().toISOString(),
      reason:    'patchAgentLua regex did not match after spawn',
      module_tx: moduleId,
      orphan_pid: newPid,
      action:    'Manually edit agent.lua PROVER_PID, or rotate via Set-Prover and discard this PID.',
    };
    try { writeFileSync(ROLLBACK_PATH, JSON.stringify(marker, null, 2) + '\n', 'utf-8'); }
    catch (e) { console.error('  (also failed to write rollback marker:', e.message, ')'); }
    die(`Could not find PROVER_PID line in agent.lua — patch failed. Orphan PID ${newPid} recorded in ${ROLLBACK_PATH}.`);
  }

  const tmp = AGENT_PATH + '.tmp';
  writeFileSync(tmp, patched, 'utf-8');   // write full content to tmp
  renameSync(tmp, AGENT_PATH);            // atomic swap — never leaves a partial file
  console.log('  agent.lua atomically updated.');
}

// ── Step 7: Sanity-read agent.lua ────────────────────────────────────────────
// Read back the file and confirm the PID is actually present.
// Catches regex mismatch, encoding issues, or a stale inode.

function verifyPatch(newPid) {
  step(7, 'Verifying patch was written correctly...');
  const written = readFileSync(AGENT_PATH, 'utf-8');
  if (!written.includes(newPid)) {
    die(`agent.lua was written but does not contain PID "${newPid}". ` +
        'Manual inspection required — do not reload the orchestrator.');
  }
  console.log('  ✓ PID confirmed present in agent.lua.');
}

// ── Step 8: Log result + print reload instructions ───────────────────────────

function finalise(moduleId, pid, bindingVerified) {
  step(8, 'Logging result and printing reload instructions...');

  const entry = JSON.stringify({
    ts:              new Date().toISOString(),
    module_tx:       moduleId,
    seer_pid:        pid,
    binding_verified: bindingVerified,
    wasm_smoke:      true,
  });
  appendFileSync(LOG_PATH, entry + '\n', 'utf-8');
  console.log('  Appended to cutover.log.');

  console.log(`
  Reload options:

  A) Full reload (picks up all agent.lua changes):
       aos <orchestrator-pid> < agent.lua

  B) Hot-patch PID only (no reload):
       Send({ Target = <orchestrator-pid>, Action = "Set-Prover",
              Tags = { ["Prover-Pid"] = "${pid}" } })
       Send({ Target = <orchestrator-pid>, Action = "Flush-Buffer" })

  C) Smoke test after reload:
       Send({ Target = <orchestrator-pid>, Action = "Scan-Page",
              Data   = "<input type='hidden' value='test'>",
              Tags   = { ["Page-URL"] = "http://localhost/", ["Level"] = "1" } })
       -- Expect: Proof-Result with satisfiable = true
`);
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  console.log('=== Paxiom Seer Cutover ===');
  console.log('WASM :', WASM_PATH);
  console.log('Node :', HB_URL);
  console.log('Log  :', LOG_PATH);

  const wallet = JSON.parse(readFileSync(path.join(HOME, '.aos.json'), 'utf-8'));

  // Pre-spawn assertion: fail fast if agent.lua's PROVER_PID line won't match
  // the patch regex. Cheaper than orphaning a new module after a successful spawn.
  if (!PROVER_PID_RE.test(readFileSync(AGENT_PATH, 'utf-8'))) {
    die('agent.lua PROVER_PID line does not match patch regex — fix before spawning.');
  }

  const moduleId = await upload(wallet);
  await waitForModule(moduleId);
  const pid = await spawnSeer(wallet, moduleId);
  await verifyBinding(pid, moduleId);   // hard-fails on mismatch
  await smokeTestWasm();
  patchAgentLua(pid, moduleId);         // atomic write
  verifyPatch(pid);                     // read-back sanity check
  finalise(moduleId, pid, true);

  console.log('\n✓ Cutover complete and self-validated.');
  console.log('  Module TX:', moduleId);
  console.log('  Seer PID: ', pid);
}

// Only run main() when invoked directly (not when imported by tests for
// SMOKE_FIXTURE / STEPS — see audit I-2).
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch(e => {
    console.error('\nFATAL:', e.message);
    process.exit(1);
  });
}
