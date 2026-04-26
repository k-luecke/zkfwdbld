// direct_spawn.js — bypasses aoconnect's toDataItemSigner chain entirely.
// Uses @dha-team/arbundles ArweaveSigner directly so we can inspect the owner.
if (typeof crypto === 'undefined') { global.crypto = require('node:crypto').webcrypto; }

const { ArweaveSigner, createData } = require('@dha-team/arbundles/node');
const { readFileSync }  = require('fs');
const path = require('path');

const MODULE_TX = 'j_yTLMEoAs2mfGI8-mWxL_pSTS9PQY4d5JH88EP8fT0';
const SCHEDULER = 'TZ7o7SIZ06ZEJ14lXwVtng1EtSx60QkPy-kh-kdAXog';
const MU_URL    = 'https://ao-mu-1.onrender.com';

async function main() {
  const wallet = JSON.parse(readFileSync(path.resolve(process.env.HOME, '.aos.json'), 'utf-8'));
  const signer = new ArweaveSigner(wallet);

  console.log('publicKey length:', signer.publicKey?.length);

  const tags = [
    { name: 'Data-Protocol', value: 'ao' },
    { name: 'Variant',       value: 'ao.TN.1' },
    { name: 'Type',          value: 'Process' },
    { name: 'Module',        value: MODULE_TX },
    { name: 'Scheduler',     value: SCHEDULER },
    { name: 'SDK',           value: 'aoconnect' },
  ];

  const dataItem = createData(' ', signer, { tags });

  await dataItem.sign(signer);

  const raw = dataItem.getRaw();
  console.log('data item bytes:', raw.length);
  console.log('owner bytes (first 8):', Buffer.from(raw).slice(64, 72).toString('hex'));
  console.log('item id:', dataItem.id);
  console.log('tags on item:', dataItem.tags);

  console.log('\nPOSTing to MU...');
  const res = await fetch(MU_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream', Accept: 'application/json' },
    body: raw,
  });

  const body = await res.text();
  console.log('MU status:', res.status);
  console.log('MU response:', body);
}

main().catch(e => console.error('ERROR:', e.message));
