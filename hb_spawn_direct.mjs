// hb_spawn_direct.mjs
// Bypasses ao-core-libs signing (broken Qr signer: SHA256 double-hash mismatch).
// Uses ArweaveSigner from @dha-team/arbundles directly — same path as direct_spawn.js
// but targets the HyperBEAM /push endpoint instead of the dead legacy MU.
//
// Usage: node hb_spawn_direct.mjs

import { ArweaveSigner, createData } from '@dha-team/arbundles/node';
import { readFileSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const HOME = process.env.HOME;

const MODULE_TX      = 'j_yTLMEoAs2mfGI8-mWxL_pSTS9PQY4d5JH88EP8fT0';
const HB_URL         = 'https://push.forward.computer';
const META_TIMEOUT   = 8_000;   // ms
const PUSH_TIMEOUT   = 30_000;  // ms — HyperBEAM can be slow to ack
const MAX_ATTEMPTS   = 4;
const BACKOFF_BASE   = 2_000;   // ms — doubles each retry (2s, 4s, 8s)
const RETRY_STATUSES = new Set([429, 500, 502, 503, 504]);

// Wraps fetch with an AbortController deadline.
async function fetchWithTimeout(url, opts, timeoutMs) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(url, { ...opts, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function main() {
  const wallet = JSON.parse(readFileSync(path.join(HOME, '.aos.json'), 'utf-8'));
  const signer = new ArweaveSigner(wallet);

  // ── 1. Fetch scheduler address ─────────────────────────────────────────────
  console.log('Fetching scheduler from HyperBEAM node...');
  let metaRes;
  try {
    metaRes = await fetchWithTimeout(
      `${HB_URL}/~meta@1.0/info/address`, {}, META_TIMEOUT
    );
  } catch (e) {
    throw new Error(`Meta fetch failed (timeout or network): ${e.message}`);
  }
  if (!metaRes.ok) throw new Error(`Meta fetch HTTP ${metaRes.status}`);
  const scheduler = (await metaRes.text()).trim();
  console.log('Scheduler:', scheduler);

  // ── 2. Build + sign data item ──────────────────────────────────────────────
  // Tags match aoconnect's spawnWith() params exactly.
  const tags = [
    { name: 'device',            value: 'process@1.0'      },
    { name: 'scheduler-device',  value: 'scheduler@1.0'    },
    { name: 'push-device',       value: 'push@1.0'         },
    { name: 'execution-device',  value: 'genesis-wasm@1.0' },
    { name: 'Authority',         value: scheduler           },
    { name: 'Scheduler',         value: scheduler           },
    { name: 'Module',            value: MODULE_TX           },
    { name: 'signing-format',    value: 'ans104'            },
    { name: 'accept-bundle',     value: 'true'              },
    { name: 'accept-codec',      value: 'httpsig@1.0'      },
    { name: 'App-Name',          value: 'Paxiom-Seer'      },
    { name: 'Entity-Type',       value: 'Seer-Agent'       },
    { name: 'Data-Protocol',     value: 'ao'               },
    { name: 'Type',              value: 'Process'           },
    { name: 'Variant',           value: 'ao.N.1'            },
  ];

  const dataItem = createData('1984', signer, { tags });
  await dataItem.sign(signer);

  const raw = dataItem.getRaw();
  console.log('Data item signed. Bytes:', raw.length, '| ID:', dataItem.id);

  // Local verify — catches key issues before hitting the wire.
  const { DataItem } = await import('@dha-team/arbundles');
  const valid = await DataItem.verify(raw);
  if (!valid) throw new Error('Data item failed local verification — abort');
  console.log('Local signature valid: true');

  // ── 3. POST with retry + backoff ───────────────────────────────────────────
  console.log(`\nPOSTing to ${HB_URL}/push ...`);

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    let res;
    try {
      res = await fetchWithTimeout(
        `${HB_URL}/push`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/ans104',
            'codec-device': 'ans104@1.0',
          },
          body: raw,
        },
        PUSH_TIMEOUT
      );
    } catch (e) {
      const isAbort = e.name === 'AbortError';
      console.error(`Attempt ${attempt}/${MAX_ATTEMPTS} — ${isAbort ? 'timed out' : e.message}`);
      if (attempt < MAX_ATTEMPTS) {
        const delay = BACKOFF_BASE * (2 ** (attempt - 1));
        console.log(`  Waiting ${delay / 1000}s before retry...`);
        await new Promise(r => setTimeout(r, delay));
        continue;
      }
      throw new Error(`All ${MAX_ATTEMPTS} attempts failed: last error: ${e.message}`);
    }

    const pid = res.headers.get('process');
    if (pid) {
      console.log('\n========================================');
      console.log('SUCCESS — Process ID:', pid);
      console.log('========================================');
      console.log(`\nConnect with: aos ${pid}`);
      return;
    }

    if (RETRY_STATUSES.has(res.status) && attempt < MAX_ATTEMPTS) {
      const retryAfter = Number(res.headers.get('retry-after') ?? 0) * 1000;
      const delay = retryAfter || BACKOFF_BASE * (2 ** (attempt - 1));
      console.error(`Attempt ${attempt}/${MAX_ATTEMPTS} — HTTP ${res.status}, retrying in ${delay / 1000}s`);
      await new Promise(r => setTimeout(r, delay));
      continue;
    }

    // Non-retryable or final attempt.
    const body = await res.text().catch(() => '(unreadable body)');
    if (res.ok || res.status === 201 || res.status === 202) {
      console.log('Accepted (no process header) — check body for ID');
      console.log('Body:', body.slice(0, 500));
    } else {
      console.error(`Spawn failed — HTTP ${res.status}`);
      console.error('Body:', body.slice(0, 500));
      process.exit(1);
    }
    return;
  }
}

main().catch(e => {
  console.error('ERROR:', e.message);
  if (e.cause) console.error('CAUSE:', e.cause?.message ?? e.cause);
  console.error(e.stack?.split('\n').slice(0, 4).join('\n'));
  process.exit(1);
});
