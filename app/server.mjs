import { existsSync, createReadStream } from "node:fs";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildPacketSnapshot } from "./packet_snapshot.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const STATIC_DIR = path.join(__dirname, "static");
const packetDirArg = process.argv[2];
const requestedPort = Number.parseInt(process.argv[3] || process.env.PORT || "4173", 10);

function fileExists(filePath) {
  return existsSync(filePath);
}

function sendJson(res, payload, statusCode = 200) {
  res.writeHead(statusCode, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(payload));
}

function sendFile(res, filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const contentType = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8"
  }[ext] || "text/plain; charset=utf-8";

  res.writeHead(200, { "Content-Type": contentType });
  createReadStream(filePath).pipe(res);
}

const server = createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");

  if (url.pathname === "/api/packet") {
    try {
      sendJson(res, { ok: true, packet: buildPacketSnapshot(packetDirArg) });
    } catch (error) {
      sendJson(
        res,
        {
          ok: false,
          error: error.message,
          packet_dir: packetDirArg || "artifacts/polsia-demo-packet"
        },
        500
      );
    }
    return;
  }

  const normalizedPath = url.pathname === "/" ? "/index.html" : url.pathname;
  const filePath = path.join(STATIC_DIR, normalizedPath);

  if (fileExists(filePath) && filePath.startsWith(STATIC_DIR)) {
    sendFile(res, filePath);
    return;
  }

  res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
  res.end("Not found");
});

server.listen(requestedPort, "127.0.0.1", () => {
  console.log(
    JSON.stringify(
      {
        app: "zkfwdbld-viewer",
        url: `http://127.0.0.1:${requestedPort}`,
        packet_dir: packetDirArg || "artifacts/polsia-demo-packet"
      },
      null,
      2
    )
  );
});
