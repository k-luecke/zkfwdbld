// deploy_seer.js — AO Network deployment bridge for the Seer prover module.
// Bypasses the aos CLI by using @permaweb/aoconnect directly over Node.js.
// Run from ~/zkfwdbld after seer.wasm has been built and stripped.
//
// Usage:  node deploy_seer.js

const { spawn, createDataItemSigner } = require('@permaweb/aoconnect');
const { readFileSync }                = require('fs');
const path                            = require('path');

async function deploy() {
  // ── 1. Load artifacts ────────────────────────────────────────────────────
  console.log('Reading Seer Brain (seer.wasm)...');
  const wasmPath   = path.resolve(__dirname, 'seer.wasm');
  const walletPath = path.resolve(process.env.HOME, '.aos.json');

  const wasm   = readFileSync(wasmPath);
  const wallet = JSON.parse(readFileSync(walletPath, 'utf-8'));

  console.log(`  wasm   : ${wasmPath}  (${wasm.length} bytes)`);
  console.log(`  wallet : ${walletPath}`);

  // ── 2. Spawn AO process ───────────────────────────────────────────────────
  // IMPORTANT: `module` is the AOS bootloader ID (a string), NOT the wasm bytes.
  // The compiled seer.wasm binary goes in `data` — the bootloader loads it.
  console.log('\nBroadcasting to Arweave gateways...');
  const processId = await spawn({
    module    : 'SBNpk70S_rg_bE_ZpYhv-YvfcBC-S66_pYv72d-6IvU', // standard AOS module
    scheduler : '_GQbaH9vunE_PAsv79E-8659-E4973-5v55_G6-B',
    signer    : createDataItemSigner(wallet),
    data      : wasm,                                             // seer.wasm payload
    tags      : [
      { name: 'App-Name',    value: 'Paxiom-Seer'  },
      { name: 'Entity-Type', value: 'Seer-Agent'   },
      { name: 'Version',     value: '0.1.0'         },
      { name: 'Field',       value: 'Goldilocks-64' },
    ],
  });

  // ── 3. Report ─────────────────────────────────────────────────────────────
  console.log('-------------------------------------------');
  console.log('SUCCESS: THE SEER IS LIVE');
  console.log('Process ID:', processId);
  console.log('-------------------------------------------');
  console.log('\nNext step — paste into agent.lua:');
  console.log(`  PROVER_PID = "${processId}"`);
  console.log('\nThen load the orchestrator:');
  console.log('  aos <your-orchestrator> < agent.lua');
}

deploy().catch(e => {
  console.error('\nDeployment Failed:', e.message ?? e);
  process.exit(1);
});
