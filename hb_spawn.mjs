// hb_spawn.mjs — ESM import fixes the ao-core-libs.default.init CJS issue
import { connect, createSigner } from '@permaweb/aoconnect';
import { readFileSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const HOME = process.env.HOME;

const MODULE_TX = 'j_yTLMEoAs2mfGI8-mWxL_pSTS9PQY4d5JH88EP8fT0';
const SCHEDULER = 'ZqkuoHZ3GTSCVh96BUgO0wlszuOfzFcerd_zN5W4xTU';
const HB_URL    = 'http://hyperbeam.permaweb.black:10000';

const wallet = JSON.parse(readFileSync(path.join(HOME, '.aos.json'), 'utf-8'));
const signer  = createSigner(wallet);

console.log('Mode: HyperBEAM mainnet (ESM)');
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
  console.error('FAILED:', e.message);
  if (e.cause)  console.error('CAUSE:',  e.cause?.message ?? e.cause);
  if (e.cause?.cause) console.error('ROOT:', e.cause.cause?.message ?? e.cause.cause);
  if (e.details) console.error('DETAILS:', JSON.stringify(e.details));
  console.error(e.stack?.split('\n').slice(0,5).join('\n'));
}
