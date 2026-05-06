// seer_eval/ops_runner.mjs - minimal internal ops loop for queued agent actions.

import { readFileSync } from 'fs';
import path from 'path';

import { parseMessageDraftFile } from './message_ingest.mjs';
import { policyReviewedOutboundMessages } from './message_pipeline.mjs';
import { loadOutboundMessagePolicy } from './message_policy.mjs';
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

export function runOutboundMessageOpsLoop(queuePath, outputDir, options = {}) {
  const policy =
    options.policy_path ? loadOutboundMessagePolicy(options.policy_path) : undefined;
  const drafts = parseMessageDraftFile(queuePath);
  const artifacts = policyReviewedOutboundMessages(drafts, policy);
  const result = exportFindingReportSet(artifacts, outputDir, {
    title: options.title ?? 'Ops Queue Outbound Message Review',
  });

  return {
    queue_path: queuePath,
    policy_path: options.policy_path ?? null,
    action_count: drafts.length,
    ...result,
  };
}

export function defaultOpsPaths(rootDir = process.cwd()) {
  return {
    queue_path: path.join(rootDir, 'ops', 'queue', 'outbound_messages.json'),
    policy_path: path.join(rootDir, 'ops', 'policies', 'outbound_message_policy.json'),
    output_dir: path.join(rootDir, 'artifacts', 'ops-outbound-review'),
  };
}
