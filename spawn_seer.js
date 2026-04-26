// spawn_seer.js — Phase 2 only. Module is anchored, no re-upload needed.
// Updated for @permaweb/aoconnect 0.0.93 which uses connect({ signer }) API.
//
// Usage:  node spawn_seer.js
if (typeof crypto === 'undefined') { global.crypto = require('node:crypto').webcrypto; }

const { connect, createSigner } = require('@permaweb/aoconnect');
const { readFileSync } = require('fs');
const path = require('path');

const MODULE_TX   = 'j_yTLMEoAs2mfGI8-mWxL_pSTS9PQY4d5JH88EP8fT0';
const SCHEDULER   = 'TZ7o7SIZ06ZEJ14lXwVtng1EtSx60QkPy-kh-kdAXog';
const GW_BASE     = 'https://arweave.net';
const MAX_RETRIES       = 6;
const RETRY_MS          = 30_000;
const GW_POLL_MS        = 60_000;   // 1-min re-check when module not yet visible
const GW_REQUEST_MS     = 15_000;   // per-fetch deadline inside waitForModule
const PREFLIGHT_BUDGET  = 10 * 60_000; // 10 min total preflight ceiling

// Wraps fetch with an AbortController deadline.
function fetchTimeout(url, opts, ms) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  return fetch(url, { ...opts, signal: ctrl.signal }).finally(() => clearTimeout(t));
}

// ── Pre-flight: verify module TX is on-chain and carries AO tags ─────────────
async function waitForModule() {
  const url = `${GW_BASE}/graphql`;
  const query = JSON.stringify({
    query: `{ transaction(id: "${MODULE_TX}") {
      id
      tags { name value }
    } }`,
  });

  const deadline = Date.now() + PREFLIGHT_BUDGET;

  for (;;) {
    if (Date.now() >= deadline) {
      console.error('[preflight] Global budget exceeded — aborting.');
      process.exit(1);
    }
    try {
      const res  = await fetchTimeout(url, {
        method  : 'POST',
        headers : { 'Content-Type': 'application/json' },
        body    : query,
      }, GW_REQUEST_MS);
      const json = await res.json();
      const tx   = json?.data?.transaction;

      if (!tx) {
        console.log(`[preflight] TX ${MODULE_TX} not yet visible on gateway — waiting ${GW_POLL_MS/1000}s...`);
        await new Promise(r => setTimeout(r, GW_POLL_MS));
        continue;
      }

      const tags   = Object.fromEntries((tx.tags || []).map(t => [t.name, t.value]));
      const proto  = tags['Data-Protocol'];
      const type   = tags['Type'];
      const fmt    = tags['Module-Format'];
      const encIn  = tags['Input-Encoding'];
      const encOut = tags['Output-Encoding'];

      console.log('[preflight] TX found on gateway:');
      console.log(`  Data-Protocol  : ${proto  ?? '(missing)'}`);
      console.log(`  Type           : ${type   ?? '(missing)'}`);
      console.log(`  Module-Format  : ${fmt    ?? '(missing)'}`);
      console.log(`  Input-Encoding : ${encIn  ?? '(missing)'}`);
      console.log(`  Output-Encoding: ${encOut ?? '(missing)'}`);

      const missing = [];
      if (proto !== 'ao')      missing.push('Data-Protocol=ao');
      if (type  !== 'Module')  missing.push('Type=Module');
      if (!encIn)              missing.push('Input-Encoding');
      if (!encOut)             missing.push('Output-Encoding');

      if (missing.length > 0) {
        console.error(`[preflight] FATAL: required AO tags missing: ${missing.join(', ')}`);
        console.error('  Re-run deploy_paxiom.js to re-upload with the full tag set.');
        process.exit(1);
      }

      console.log('[preflight] Module is indexed with correct AO tags. Proceeding to spawn.\n');
      return;
    } catch (e) {
      const reason = e.name === 'AbortError' ? 'request timed out' : e.message;
      console.warn(`[preflight] Gateway query failed: ${reason} — retrying in ${GW_POLL_MS/1000}s`);
      await new Promise(r => setTimeout(r, GW_POLL_MS));
    }
  }
}

async function main() {
  const wallet = JSON.parse(
    readFileSync(path.resolve(process.env.HOME, '.aos.json'), 'utf-8')
  );

  await waitForModule();

  // In legacy mode (the default), connect() does NOT propagate signer into env.
  // The signer must be passed explicitly to each spawn() / message() call.
  const { spawn } = connect();
  const signer = createSigner(wallet);

  for (let i = 1; i <= MAX_RETRIES; i++) {
    console.log(`Attempt ${i}/${MAX_RETRIES} — module ${MODULE_TX}`);
    try {
      const processId = await spawn({
        module    : MODULE_TX,
        scheduler : SCHEDULER,
        signer,
        tags      : [
          { name: 'App-Name',    value: 'Paxiom-Seer' },
          { name: 'Entity-Type', value: 'Seer-Agent'  },
          { name: 'Module-TX',   value: MODULE_TX      },
        ],
      });

      console.log('-------------------------------------------');
      console.log('SUCCESS: THE SEER IS LIVE');
      console.log('Module  TX :', MODULE_TX);
      console.log('Process ID :', processId);
      console.log('-------------------------------------------');
      console.log(`\nPaste into agent.lua:\n  PROVER_PID = "${processId}"`);
      return;

    } catch (e) {
      const msg = e.message ?? String(e);
      console.warn(`  Attempt ${i} failed: ${msg.split('\n')[0]}`);
      if (i < MAX_RETRIES) {
        console.log(`  Waiting ${RETRY_MS / 1000}s...`);
        await new Promise(r => setTimeout(r, RETRY_MS));
      }
    }
  }

  console.error(`\nAll ${MAX_RETRIES} attempts exhausted.`);
  console.error('Module is on-chain but the SU router may still be catching up.');
  console.error('Re-run in 5–10 min.');
}

main();
