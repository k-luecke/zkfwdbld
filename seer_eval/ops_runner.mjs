// seer_eval/ops_runner.mjs - minimal internal ops loop for queued agent actions.

import { readFileSync } from 'fs';
import path from 'path';

import { reviewedArtifactsFromDraftFile } from './message_ingest.mjs';
import { exportFindingReportSet } from './report_exporter.mjs';

function readJson(filePath) {
  return JSON.parse(readFileSync(filePath, 'utf-8'));
}

export function loadOpsQueue(filePath) {
  const parsed = readJson(filePath);
  const actions = Array.isArray(parsed) ? parsed : parsed.actions ?? [];

  if (!Array.isArray(actions)) {
    throw new Error('Ops queue file must contain an array or a { "actions": [...] } object.');
  }

  return actions;
}

export function runOutboundMessageOpsLoop(queuePath, outputDir) {
  const queue = loadOpsQueue(queuePath);
  const tempDraftPath = queuePath;
  const artifacts = reviewedArtifactsFromDraftFile(tempDraftPath);
  const result = exportFindingReportSet(artifacts, outputDir, {
    title: 'Ops Queue Outbound Message Review',
  });

  return {
    queue_path: queuePath,
    action_count: queue.length,
    ...result,
  };
}

export function defaultOpsPaths(rootDir = process.cwd()) {
  return {
    queue_path: path.join(rootDir, 'ops', 'queue', 'outbound_messages.json'),
    output_dir: path.join(rootDir, 'artifacts', 'ops-outbound-review'),
  };
}
