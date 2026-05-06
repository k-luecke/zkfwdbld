import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { writePacketSnapshot } from "./packet_snapshot.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..");
const DEFAULT_PACKET_DIR = path.join(REPO_ROOT, "artifacts", "polsia-demo-packet");

const packetDir = process.argv[2];
const outputPath = process.argv[3];

// Audit L-10 (#34): the Tauri build invokes this script unconditionally via
// `beforeBuildCommand`, so a missing `artifacts/polsia-demo-packet/` directory
// (typical on a fresh clone or in offline development) used to abort the
// build. Allow callers to opt in to a soft no-op when the packet source is
// not present, so `tauri dev` / `tauri build` work without first running the
// full packet generator. Set `SEER_REQUIRE_PACKET=1` (or pass an explicit
// packet dir on argv) to restore the strict behaviour.
const resolvedPacketDir = packetDir
  ? path.resolve(REPO_ROOT, packetDir)
  : DEFAULT_PACKET_DIR;

const requirePacket = process.env.SEER_REQUIRE_PACKET === "1" || Boolean(packetDir);

if (!existsSync(resolvedPacketDir)) {
  if (requirePacket) {
    console.error(
      `generate_packet_json: ERROR — packet directory not found: ${resolvedPacketDir}`
    );
    process.exit(1);
  }
  console.warn(
    `generate_packet_json: packet directory not found (${resolvedPacketDir}); ` +
      `skipping snapshot generation. Set SEER_REQUIRE_PACKET=1 to fail instead.`
  );
  console.log(
    JSON.stringify(
      { ok: true, skipped: true, reason: "packet_dir_missing", packet_dir: resolvedPacketDir },
      null,
      2
    )
  );
  process.exit(0);
}

const result = writePacketSnapshot({ packetDir, outputPath });

console.log(
  JSON.stringify(
    {
      ok: true,
      output_path: result.outputPath,
      packet_type: result.packet.packet_type,
      generated_at: result.packet.generated_at
    },
    null,
    2
  )
);
