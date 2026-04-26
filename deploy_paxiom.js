// deploy_paxiom.js — Two-phase AO native module deployment.
// Phase 1: Upload seer.wasm to Arweave via Turbo (free, no AR needed).
// Phase 2: Spawn an AO process using the anchored module TX ID.
//
// Usage:  node deploy_paxiom.js
if (typeof crypto === 'undefined') { global.crypto = require('node:crypto').webcrypto; }

const { TurboFactory }   = require('@ardrive/turbo-sdk');
const { connect, createSigner } = require('@permaweb/aoconnect');
const { readFileSync, createReadStream, statSync } = require('fs');
const path = require('path');

const SCHEDULER = '_GQbaH9vunE_PAsv79E-8659-E4973-5v55_G6-B';

async function deploy() {
  try {
    const wallet   = JSON.parse(readFileSync(path.resolve(process.env.HOME, '.aos.json'), 'utf-8'));
    const wasmPath = path.resolve(__dirname, 'target', 'wasm32-unknown-unknown', 'release', 'zkfwdbld.wasm');
    const wasmSize = statSync(wasmPath).size;

    // ── PHASE 1: Upload via Turbo with full AO module tag set ─────────────────
    // The AO scheduler validates these tags before accepting the module TX.
    // Missing any of Data-Protocol, Type, or Module-Format → spawn rejected.
    console.log(`Phase 1: Uploading via Turbo (${wasmSize} bytes)...`);
    const turbo  = TurboFactory.authenticated({ privateKey: wallet });
    const result = await turbo.uploadFile({
      fileStreamFactory: () => createReadStream(wasmPath),
      fileSizeFactory:   () => wasmSize,
      dataItemOpts: {
        tags: [
          { name: 'Data-Protocol',  value: 'ao' },
          { name: 'Variant',        value: 'ao.TN.1' },
          { name: 'Type',           value: 'Module' },
          { name: 'Module-Format',  value: 'wasm32-unknown-unknown' },
          { name: 'Input-Encoding', value: 'JSON-V1' },
          { name: 'Output-Encoding',value: 'JSON-V1' },
          { name: 'Content-Type',   value: 'application/wasm' },
          { name: 'Memory-Limit',   value: '500-mb' },
          { name: 'Compute-Limit',  value: '9000000000000' },
          { name: 'App-Name',       value: 'Paxiom-Seer' },
        ],
      },
    });

    const moduleId = result.id;
    console.log(`Module anchored! TX ID: ${moduleId}`);
    console.log('Phase 2: Spawning AO process...');

    // ── PHASE 2: Spawn using corrected aoconnect 0.0.93 API ──────────────────
    // Signer is baked into connect(); spawn() no longer takes signer directly.
    const { spawn } = connect({ signer: createSigner(wallet) });

    const processId = await spawn({
      module    : moduleId,
      scheduler : SCHEDULER,
      tags      : [
        { name: 'App-Name',    value: 'Paxiom-Seer' },
        { name: 'Entity-Type', value: 'Seer-Agent'  },
        { name: 'Module-TX',   value: moduleId       },
      ],
    });

    console.log('-------------------------------------------');
    console.log('SUCCESS: THE SEER IS LIVE');
    console.log('Module  TX :', moduleId);
    console.log('Process ID :', processId);
    console.log('-------------------------------------------');
    console.log(`\nPaste into agent.lua:\n  PROVER_PID = "${processId}"`);

  } catch (e) {
    console.error('Deployment Failed:', e.message ?? e);
    process.exit(1);
  }
}
deploy();
