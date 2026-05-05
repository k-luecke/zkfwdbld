// Inject Web Crypto for Node.js < v20
if (typeof crypto === 'undefined') {
  global.crypto = require('node:crypto').webcrypto;
}

const { spawn, createDataItemSigner } = require('@permaweb/aoconnect');
const { readFileSync } = require('fs');
const path = require('path');
const os = require('os');

const WALLET_PATH = process.env.AOS_WALLET || path.join(os.homedir(), '.aos.json');

async function deploy() {
  try {
    const wasm   = readFileSync('./seer.wasm');
    const wallet = JSON.parse(readFileSync(WALLET_PATH, 'utf-8'));

    console.log(`Spawning Seer-Agent (${wasm.length} bytes)...`);
    const processId = await spawn({
      module    : 'ghSkge2sIUD_F00ym5sEimC63BDBuBrq4b5OcwxOjiw', // AOS-WASM64 module
      scheduler : '_GQbaH9vunE_PAsv79E-8659-E4973-5v55_G6-B',
      signer    : createDataItemSigner(wallet),
      data      : wasm,
      tags      : [
        { name: 'App-Name',    value: 'Paxiom-Seer' },
        { name: 'Entity-Type', value: 'Seer-Agent'  },
      ],
    });

    console.log('-------------------------------------------');
    console.log('SUCCESS: THE SEER IS ANCHORED');
    console.log('Process ID:', processId);
    console.log('-------------------------------------------');
  } catch (e) {
    console.error('Deployment Failed:', e);
    process.exit(1);
  }
}
deploy();
