// hb_spawn.js — uses aoconnect mainnet/HyperBEAM mode (no legacy MU)
if (typeof crypto === 'undefined') { global.crypto = require('node:crypto').webcrypto; }

const { connect, createSigner } = require('@permaweb/aoconnect');
const { readFileSync } = require('fs');
const path = require('path');

const MODULE_TX = 'j_yTLMEoAs2mfGI8-mWxL_pSTS9PQY4d5JH88EP8fT0';
const SCHEDULER = 'n_XZJhUnmldNFo4dhajoPZWhBXuJk-OcQr5JQ49c4Zo';  // validated mainnet scheduler
const HB_URL    = 'https://tee-6.forward.computer';

async function main() {
  const wallet = JSON.parse(readFileSync(path.resolve(process.env.HOME, '.aos.json'), 'utf-8'));
  const signer  = createSigner(wallet);

  console.log('Mode: HyperBEAM mainnet');
  console.log('Node:', HB_URL);

  const { spawn } = connect({ MODE: 'mainnet', URL: HB_URL, signer });

  try {
    const pid = await spawn({
      module   : MODULE_TX,
      scheduler: SCHEDULER,
      tags: [
        { name: 'App-Name',    value: 'Paxiom-Seer' },
        { name: 'Entity-Type', value: 'Seer-Agent'  },
      ],
    });
    console.log('SUCCESS — PID:', pid);
  } catch (e) {
    console.error('FAILED:', e.message.split('\n')[0]);
  }
}

main();
