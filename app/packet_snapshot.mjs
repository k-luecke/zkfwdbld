import { readFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..");
const DEFAULT_PACKET_DIR = path.join(REPO_ROOT, "artifacts", "polsia-demo-packet");
const DEFAULT_OUTPUT_PATH = path.join(__dirname, "static", "generated", "packet.json");

function resolvePacketDir(packetDirArg) {
  return packetDirArg
    ? path.resolve(REPO_ROOT, packetDirArg)
    : DEFAULT_PACKET_DIR;
}

function readJson(filePath) {
  return JSON.parse(readFileSync(filePath, "utf8"));
}

function readText(filePath) {
  return readFileSync(filePath, "utf8");
}

function toRepoRelative(filePath) {
  return path.relative(REPO_ROOT, filePath).split(path.sep).join("/");
}

function buildBundleSnapshot(bundleMeta) {
  const manifest = readJson(bundleMeta.manifest_path);
  const handoff = readText(bundleMeta.handoff_path);
  const indexText = readText(bundleMeta.index_path);
  const items = manifest.bundles.map((bundle) => ({
    finding_id: bundle.finding_id,
    bundle_dir: toRepoRelative(bundle.bundle_dir),
    report_path: toRepoRelative(bundle.report_path),
    artifact_path: toRepoRelative(bundle.artifact_path),
    report: readText(bundle.report_path),
    artifact: readJson(bundle.artifact_path)
  }));

  return {
    key: path.basename(bundleMeta.root_dir),
    root_dir: toRepoRelative(bundleMeta.root_dir),
    handoff_path: toRepoRelative(bundleMeta.handoff_path),
    index_path: toRepoRelative(bundleMeta.index_path),
    manifest_path: toRepoRelative(bundleMeta.manifest_path),
    summary: bundleMeta.summary,
    manifest,
    handoff,
    index: indexText,
    items
  };
}

export function buildPacketSnapshot(packetDirArg) {
  const packetDir = resolvePacketDir(packetDirArg);
  if (!existsSync(packetDir)) {
    throw new Error(`Packet directory not found: ${packetDir}`);
  }

  const packetManifestPath = path.join(packetDir, "packet_manifest.json");
  if (!existsSync(packetManifestPath)) {
    throw new Error(`Packet manifest not found: ${packetManifestPath}`);
  }

  const packetManifest = readJson(packetManifestPath);
  const bundles = Object.entries(packetManifest.bundles).map(([name, meta]) => ({
    name,
    ...buildBundleSnapshot(meta)
  }));

  return {
    generated_at: packetManifest.generated_at,
    packet_type: packetManifest.packet_type,
    packet_dir: toRepoRelative(packetDir),
    overview_path: toRepoRelative(packetManifest.overview_path),
    overview: readText(packetManifest.overview_path),
    talk_track_path: toRepoRelative(path.join(packetDir, "demo_talk_track.md")),
    talk_track: readText(path.join(packetDir, "demo_talk_track.md")),
    bundles
  };
}

export function writePacketSnapshot(options = {}) {
  const packet = buildPacketSnapshot(options.packetDir);
  const outputPath = options.outputPath
    ? path.resolve(REPO_ROOT, options.outputPath)
    : DEFAULT_OUTPUT_PATH;
  mkdirSync(path.dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, JSON.stringify(packet, null, 2));
  return { outputPath, packet };
}
