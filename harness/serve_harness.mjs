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
  // Audit H-3 (#7): decode percent-escapes so `%2e%2e` cannot bypass a
  // textual `..` strip; resolve to an absolute path; reject anything
  // outside __dirname. The previous `replace(/\.\./g, '')` was a textual
  // blocklist that missed URL-encoded traversal.
  let urlPath;
  try {
    urlPath = decodeURIComponent(req.url.split('?')[0]);
  } catch {
    res.writeHead(400, { 'Content-Type': 'text/plain' });
    res.end('Bad request');
    return;
  }

  // Default route → harness page.
  const relPath = urlPath === '/' ? '/phase0_form_workflow.html' : urlPath;
  const filePath = path.resolve(__dirname, '.' + relPath);

  // Containment: resolved path must equal __dirname or be a strict child
  // (path.sep guard prevents `__dirname-evil` sibling-prefix matches).
  if (filePath !== __dirname && !filePath.startsWith(__dirname + path.sep)) {
    res.writeHead(403, { 'Content-Type': 'text/plain' });
    res.end('Forbidden');
    return;
  }

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
