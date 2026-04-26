// harness/serve_harness.mjs — Minimal static HTTP server for the Phase 0 harness.
//
// Usage: node harness/serve_harness.mjs [port]
// Default port: 7490

import { createServer } from 'http';
import { createReadStream, statSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORT      = parseInt(process.argv[2] ?? '7490', 10);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.wasm': 'application/wasm',
};

const server = createServer((req, res) => {
  // Strip query string and normalize.
  const urlPath = req.url.split('?')[0].replace(/\.\./g, '');

  // Default route → harness page.
  const relPath = urlPath === '/' ? '/phase0_form_workflow.html' : urlPath;
  const filePath = path.join(__dirname, relPath);

  let stat;
  try { stat = statSync(filePath); } catch {
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('Not found');
    return;
  }

  if (!stat.isFile()) {
    res.writeHead(403, { 'Content-Type': 'text/plain' });
    res.end('Forbidden');
    return;
  }

  const ext  = path.extname(filePath).toLowerCase();
  const mime = MIME[ext] ?? 'application/octet-stream';

  res.writeHead(200, {
    'Content-Type':   mime,
    'Content-Length': stat.size,
    'Cache-Control':  'no-store',
  });

  createReadStream(filePath).pipe(res);
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`Harness server: http://127.0.0.1:${PORT}/`);
  console.log('Press Ctrl+C to stop.');
});
