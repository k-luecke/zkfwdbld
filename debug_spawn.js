// debug_spawn.js — intercepts the MU POST to inspect the data item bytes
if (typeof crypto === 'undefined') { global.crypto = require('node:crypto').webcrypto; }

const { connect, createSigner } = require('@permaweb/aoconnect');
const { DataItem } = require('@dha-team/arbundles');
const { readFileSync } = require('fs');
const path = require('path');

const MODULE_TX = 'j_yTLMEoAs2mfGI8-mWxL_pSTS9PQY4d5JH88EP8fT0';
const SCHEDULER = '_GQ33BkPtZrqxA84vM8Zk-N2aO0toNNu_C-l-rawrBA';
const MU_URL    = 'https://mu.ao-testnet.xyz';

// Patch global fetch to inspect the outgoing data item
const origFetch = globalThis.fetch;
globalThis.fetch = async (url, opts) => {
  if (typeof url === 'string' && url.startsWith(MU_URL) && opts?.body instanceof Uint8Array) {
    console.log('\n[intercept] Outgoing POST to MU — body bytes:', opts.body.length);
    try {
      const item = new DataItem(opts.body);
      console.log('[intercept] owner bytes (first 8):', Buffer.from(item.rawOwner).slice(0,8).toString('hex'));
      console.log('[intercept] owner length:', item.rawOwner?.length);
      console.log('[intercept] id:', item.id);
      console.log('[intercept] tags:', item.tags);
    } catch (e) {
      console.log('[intercept] parse error:', e.message);
    }
  }
  return origFetch(url, opts);
};

async function main() {
  const wallet = JSON.parse(readFileSync(path.resolve(process.env.HOME, '.aos.json'), 'utf-8'));
  const signer = createSigner(wallet);
  const { spawn } = connect();

  console.log('Spawning...');
  try {
    const pid = await spawn({ module: MODULE_TX, scheduler: SCHEDULER, signer });
    console.log('SUCCESS — PID:', pid);
  } catch (e) {
    console.error('FAILED:', e.message.split('\n')[0]);
  }
}

main();
