// tests/test_seer_eval.mjs — Node.js assert/strict tests for seer_eval modules.
//
// Run: node tests/test_seer_eval.mjs
// No external test runner required.

import assert from 'assert/strict';
import { mkdtempSync, readFileSync, existsSync } from 'fs';
import { tmpdir } from 'os';
import path from 'path';

import { scoreRun, LAMBDA } from '../seer_eval/score.mjs';
import { classify, PATTERN_DEFINITIONS } from '../seer_eval/classify.mjs';
import { buildRecord, appendRun } from '../seer_eval/audit.mjs';
import { loadAll, getBaselineForFamily } from '../seer_eval/registry.mjs';
import { buildFindingArtifact } from '../seer_eval/finding_artifact.mjs';
import {
  adaptHarnessFinding,
  adaptScannerFinding,
  adaptAgentFinding,
  adaptOutboundMessageAction,
} from '../seer_eval/adapters.mjs';
import { encodeHiddenInputClaim } from '../seer_eval/claim_encoder.mjs';
import { scanHarnessHtml, artifactsFromHarnessHtml } from '../seer_eval/harness_pipeline.mjs';
import { parseMessageDraftFile, reviewedArtifactsFromDraftFile } from '../seer_eval/message_ingest.mjs';
import { defaultOutboundMessages, evaluateOutboundMessagePolicy } from '../seer_eval/message_policy.mjs';
import { defaultOpsPaths, loadOpsQueue, runOutboundMessageOpsLoop } from '../seer_eval/ops_runner.mjs';
import {
  artifactsFromOutboundMessages,
  reviewedOutboundMessageArtifacts,
} from '../seer_eval/message_pipeline.mjs';
import { artifactsFromScannerFindings, verifiedScannerArtifacts } from '../seer_eval/scanner_pipeline.mjs';
import {
  buildReportSummary,
  renderEngineeringHandoff,
  renderFindingReport,
  renderFindingReportSet,
} from '../seer_eval/report_renderer.mjs';
import { exportFindingReportSet } from '../seer_eval/report_exporter.mjs';
import { buildDemoPacket } from '../seer_eval/demo_packet.mjs';
import { median, mad, tagOutliers } from '../consolidate_baselines.mjs';

// ── Test infrastructure ───────────────────────────────────────────────────────

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (e) {
    console.error(`  ✗ ${name}`);
    console.error(`      ${e.message}`);
    failed++;
  }
}

function tmpDir() {
  return mkdtempSync(path.join(tmpdir(), 'seer_test_'));
}

// ── 1. scoreRun — transport_leak_override ────────────────────────────────────

console.log('\n1. scoreRun — transport leak override');

test('transport_leaks=true → composite=0 and all tier scores zero', () => {
  const r = scoreRun({}, { transport_leaks: true }, {}, {});
  assert.equal(r.composite, 0);
  assert.equal(r.breakdown.transport_leak_override, true);
  assert.equal(r.breakdown.outcome, 0);
  assert.equal(r.breakdown.efficiency, 0);
  assert.equal(r.breakdown.discipline, 0);
  assert.equal(r.breakdown.adaptation, 0);
});

test('transport_leaks=false does not trigger override', () => {
  const r = scoreRun({ outcome: 'SUCCESS', successful_transitions: 5, total_actions: 5, retries: 0 },
                     { transport_leaks: false }, {}, {});
  assert.equal(r.breakdown.transport_leak_override, false);
  assert.ok(r.composite > 0);
});

// ── 2. scoreRun — outcome tier ────────────────────────────────────────────────

console.log('\n2. scoreRun — outcome tier');

test('SUCCESS outcome → O=1.0 before penalties', () => {
  const r = scoreRun({ outcome: 'SUCCESS', successful_transitions: 4, total_actions: 4 }, {}, {}, {});
  assert.equal(r.breakdown.outcome.raw, 1.0);
});

test('SAFE_ABORT outcome → O=0.4 raw', () => {
  const r = scoreRun({ outcome: 'SAFE_ABORT', successful_transitions: 2, total_actions: 3 }, {}, {}, {});
  assert.equal(r.breakdown.outcome.raw, 0.4);
});

test('FAIL outcome → O=0.0', () => {
  const r = scoreRun({ outcome: 'FAIL' }, {}, {}, {});
  assert.equal(r.breakdown.outcome.raw, 0.0);
});

test('banned_violations > 0 halves outcome contribution', () => {
  const r = scoreRun({ outcome: 'SUCCESS', banned_violations: 2,
                        successful_transitions: 4, total_actions: 4 }, {}, {}, {});
  // raw=1.0, after penalty=0.5
  assert.equal(r.breakdown.outcome.after_ban_penalty, 0.5);
});

// ── 3. scoreRun — efficiency tier ────────────────────────────────────────────

console.log('\n3. scoreRun — efficiency tier');

test('perfect run: E=1.0', () => {
  const r = scoreRun({ outcome: 'SUCCESS', successful_transitions: 5, total_actions: 5, retries: 0 }, {}, {}, {});
  assert.equal(r.breakdown.efficiency.score, 1.0);
});

test('retries reduce efficiency via LAMBDA penalty', () => {
  // S_T=4, A=4, R=2 → E = 4/(4+2*2) = 4/8 = 0.5
  const r = scoreRun({ outcome: 'SUCCESS', successful_transitions: 4, total_actions: 4, retries: 2 }, {}, {}, {});
  assert.equal(r.breakdown.efficiency.score, 0.5);
});

test('LAMBDA constant is 2', () => {
  assert.equal(LAMBDA, 2);
});

// ── 4. scoreRun — discipline tier ────────────────────────────────────────────

console.log('\n4. scoreRun — discipline tier');

test('no violations, no flicker → D=1.0', () => {
  const r = scoreRun({ outcome: 'SUCCESS', successful_transitions: 3, total_actions: 3,
                        banned_violations: 0, obs_cycles_to_stability: 4, flicker_events: 0 }, {}, {}, {});
  assert.equal(r.breakdown.discipline.score, 1.0);
});

test('2 banned violations → D = max(0, 1 - 0.4) = 0.6', () => {
  const r = scoreRun({ outcome: 'SUCCESS', successful_transitions: 3, total_actions: 3,
                        banned_violations: 2, obs_cycles_to_stability: 4, flicker_events: 0 }, {}, {}, {});
  assert.equal(r.breakdown.discipline.score, 0.6);
});

test('D is clamped to 0 when violations are very high', () => {
  const r = scoreRun({ outcome: 'SUCCESS', successful_transitions: 3, total_actions: 3,
                        banned_violations: 10, obs_cycles_to_stability: 4, flicker_events: 0 }, {}, {}, {});
  assert.equal(r.breakdown.discipline.score, 0);
});

// ── 5. scoreRun — adaptation tier ────────────────────────────────────────────

console.log('\n5. scoreRun — adaptation tier');

test('no baseline → A=0, source=none', () => {
  const r = scoreRun({ outcome: 'SUCCESS', successful_transitions: 3, total_actions: 3 },
                     {}, {}, {}, null);
  assert.equal(r.breakdown.adaptation.score, 0);
  assert.equal(r.breakdown.adaptation.source, 'none');
});

test('faster than baseline (negative delta) → positive A capped at 1.0', () => {
  const baseline = { t_stable_sec_p50: 10 };
  const r = scoreRun({ outcome: 'SUCCESS', successful_transitions: 3, total_actions: 3 },
                     {}, { t_stable_delta: -15 }, {}, baseline);
  // rawBonus = -(-15/10) = 1.5 → capped at 1.0
  assert.equal(r.breakdown.adaptation.score, 1.0);
});

test('slower than baseline (positive delta) → A=0', () => {
  const baseline = { t_stable_sec_p50: 10 };
  const r = scoreRun({ outcome: 'SUCCESS', successful_transitions: 3, total_actions: 3 },
                     {}, { t_stable_delta: 5 }, {}, baseline);
  assert.equal(r.breakdown.adaptation.score, 0);
});

test('composite is rounded to 4 decimal places', () => {
  const r = scoreRun({ outcome: 'SUCCESS', successful_transitions: 3, total_actions: 3 }, {}, {}, {});
  const s = r.composite.toString();
  const decimals = s.includes('.') ? s.split('.')[1].length : 0;
  assert.ok(decimals <= 4, `Too many decimal places: ${s}`);
});

// ── 6. classify — state resolution ───────────────────────────────────────────

console.log('\n6. classify — state resolution');

test('single confident candidate → OBSERVING, correct activePattern', () => {
  const r = classify([{ pattern: 'hidden_field_leak', confidence: 0.85 }]);
  assert.equal(r.state, 'OBSERVING');
  assert.equal(r.activePattern, 'hidden_field_leak');
});

test('|top1-top2| < conflictThreshold → DEEP_OBSERVATION, activePattern=null', () => {
  const r = classify([
    { pattern: 'hidden_field_leak',          confidence: 0.80 },
    { pattern: 'form_workflow_inconsistency', confidence: 0.74 },
  ]);
  assert.equal(r.state, 'DEEP_OBSERVATION');
  assert.equal(r.activePattern, null);
});

test('no candidate above activationThreshold → UNKNOWN_PATTERN', () => {
  const r = classify([{ pattern: 'hidden_field_leak', confidence: 0.20 }]);
  assert.equal(r.state, 'UNKNOWN_PATTERN');
  assert.equal(r.activePattern, 'UNKNOWN_PATTERN');
});

test('empty candidates → UNKNOWN_PATTERN', () => {
  const r = classify([]);
  assert.equal(r.state, 'UNKNOWN_PATTERN');
});

test('null candidates → UNKNOWN_PATTERN (no crash)', () => {
  const r = classify(null);
  assert.equal(r.state, 'UNKNOWN_PATTERN');
});

// ── 7. classify — banned-inference union ─────────────────────────────────────

console.log('\n7. classify — banned-inference union');

test('banned inferences are the union across all candidates above threshold', () => {
  const r = classify([
    { pattern: 'hidden_field_leak', confidence: 0.75 },
    { pattern: 'inline_script_hint', confidence: 0.55 },
    { pattern: 'mailto_credential_leak', confidence: 0.15 }, // below threshold
  ]);
  // hidden_field_leak banned_semantic: ignore_hidden_fields, trust_form_defaults
  // inline_script_hint banned_semantic: ignore_js_comments, assume_no_hardcoded_values
  // mailto_credential_leak should NOT contribute
  assert.ok(r.bannedSemanticInferences.includes('ignore_hidden_fields'));
  assert.ok(r.bannedSemanticInferences.includes('trust_form_defaults'));
  assert.ok(r.bannedSemanticInferences.includes('ignore_js_comments'));
  assert.ok(r.bannedSemanticInferences.includes('assume_no_hardcoded_values'));
  assert.ok(!r.bannedSemanticInferences.includes('ignore_mailto_links'));
});

test('bannedSemanticInferences and bannedActionInferences are sorted', () => {
  const r = classify([
    { pattern: 'form_workflow_inconsistency', confidence: 0.90 },
    { pattern: 'hidden_field_leak',           confidence: 0.60 },
  ]);
  const sem = r.bannedSemanticInferences;
  const act = r.bannedActionInferences;
  assert.deepEqual(sem, [...sem].sort());
  assert.deepEqual(act, [...act].sort());
});

test('candidatesAboveThreshold excludes candidates below activationThreshold', () => {
  const r = classify([
    { pattern: 'hidden_field_leak',  confidence: 0.80 },
    { pattern: 'inline_script_hint', confidence: 0.25 }, // below 0.30
  ]);
  assert.equal(r.candidatesAboveThreshold.length, 1);
  assert.equal(r.candidatesAboveThreshold[0].pattern, 'hidden_field_leak');
});

// ── 8. buildRecord + appendRun ────────────────────────────────────────────────

console.log('\n8. audit — buildRecord and appendRun');

test('buildRecord returns null for all missing fields', () => {
  const r = buildRecord(null, null, null, null, null, null);
  assert.equal(r.run_id, null);
  assert.equal(r.target, null);
  assert.equal(r.metrics.outcome, null);
  assert.equal(r.cognitive_state.transport_leaks, null);
  assert.equal(r.adaptation.t_stable_delta, null);
  assert.equal(r.flags.deep_observation, null);
});

test('buildRecord preserves present values', () => {
  const r = buildRecord('run-001', 'http://x', { outcome: 'SUCCESS' },
                        { transport_leaks: false }, { t_stable_delta: -2 },
                        { deep_observation: false });
  assert.equal(r.run_id, 'run-001');
  assert.equal(r.metrics.outcome, 'SUCCESS');
  assert.equal(r.cognitive_state.transport_leaks, false);
  assert.equal(r.adaptation.t_stable_delta, -2);
});

test('appendRun writes JSONL line and atomic audit JSON', () => {
  const dir      = tmpDir();
  const runsPath  = path.join(dir, 'runs.jsonl');
  const auditPath = path.join(dir, 'audit.json');
  const record   = buildRecord('r1', 'http://example.com', { outcome: 'SUCCESS' }, {}, {}, {});

  appendRun(record, { runsPath, auditPath });

  // JSONL: one line, parseable
  const lines = readFileSync(runsPath, 'utf-8').trim().split('\n');
  assert.equal(lines.length, 1);
  const parsed = JSON.parse(lines[0]);
  assert.equal(parsed.run_id, 'r1');

  // Audit JSON: pretty-printed, same content
  const audit = JSON.parse(readFileSync(auditPath, 'utf-8'));
  assert.equal(audit.run_id, 'r1');
});

test('appendRun accumulates multiple JSONL lines', () => {
  const dir      = tmpDir();
  const runsPath  = path.join(dir, 'runs.jsonl');
  const auditPath = path.join(dir, 'audit.json');

  for (let i = 0; i < 3; i++) {
    const record = buildRecord(`r${i}`, `http://x/${i}`, {}, {}, {}, {});
    appendRun(record, { runsPath, auditPath });
  }

  const lines = readFileSync(runsPath, 'utf-8').trim().split('\n');
  assert.equal(lines.length, 3);

  // audit.json should contain the LAST record
  const audit = JSON.parse(readFileSync(auditPath, 'utf-8'));
  assert.equal(audit.run_id, 'r2');
});

// ── 9. finding artifact and adapters ─────────────────────────────────────────

console.log('\n9. verified finding artifact and adapters');

test('buildFindingArtifact fills top-level shape and defaults', () => {
  const artifact = buildFindingArtifact({
    finding_id: 'f-1',
    source: { tool: 'mock-tool' },
    claim: { family: 'hidden_field_leak' },
  });
  assert.equal(artifact.artifact_type, 'verified_finding');
  assert.equal(artifact.finding_id, 'f-1');
  assert.equal(artifact.source.tool, 'mock-tool');
  assert.equal(artifact.claim.family, 'hidden_field_leak');
  assert.equal(artifact.verification.trust_state, 'error');
});

test('all adapters emit the same artifact type', () => {
  const harness = adaptHarnessFinding({ pattern_type: 'HIDDEN_INPUT' });
  const scanner = adaptScannerFinding({});
  const agent   = adaptAgentFinding({});
  assert.equal(harness.artifact_type, 'verified_finding');
  assert.equal(scanner.artifact_type, 'verified_finding');
  assert.equal(agent.artifact_type, 'verified_finding');
});

test('harness adapter emits demo_only trust state by default', () => {
  const artifact = adaptHarnessFinding({ pattern_type: 'HIDDEN_INPUT' });
  assert.equal(artifact.source.kind, 'synthetic_harness');
  assert.equal(artifact.verification.trust_state, 'demo_only');
  assert.equal(artifact.verification.demo_only, true);
});

test('scanner adapter preserves upstream source identity', () => {
  const artifact = adaptScannerFinding({
    tool: 'mock-dast',
    source_finding_id: 'DAST-1042',
  });
  assert.equal(artifact.source.tool, 'mock-dast');
  assert.equal(artifact.source.finding_id, 'DAST-1042');
  assert.equal(artifact.source.kind, 'scanner_export');
  assert.equal(artifact.finding_id, 'scanner-dast-1042');
});

test('agent adapter preserves rationale metadata', () => {
  const artifact = adaptAgentFinding({
    rationale: 'Observed hidden state transition',
  });
  assert.equal(artifact.source.kind, 'agent_output');
  assert.equal(artifact.evidence.metadata.rationale, 'Observed hidden state transition');
});

test('outbound message adapter emits agent_action artifact shape', () => {
  const artifact = adaptOutboundMessageAction({
    message_id: 'MSG-1001',
    recipient: 'owner@customer.example',
    message_body: 'Sent by AI assistant.',
  });
  assert.equal(artifact.artifact_type, 'agent_action');
  assert.equal(artifact.action.type, 'outbound_message');
  assert.equal(artifact.action.recipient, 'owner@customer.example');
  assert.equal(artifact.verification.trust_state, 'needs_review');
});

test('encodeHiddenInputClaim is deterministic and produces prove/verify payloads', () => {
  const finding = {
    raw_string: '<input type="hidden" name="_csrf" value="phase0-static-token-aabbccdd">',
    url: 'http://127.0.0.1:7490/',
    workflow_id: 'phase0_form_workflow',
  };
  const a = encodeHiddenInputClaim(finding);
  const b = encodeHiddenInputClaim(finding);
  assert.equal(a.category, 'csrf_state');
  assert.deepEqual(a.proof_request, b.proof_request);
  assert.equal(a.proof_request.Action, 'Prove');
  assert.equal(a.verify_request_base.Action, 'Verify');
});

// ── 10. harness pipeline ─────────────────────────────────────────────────────

console.log('\n10. harness pipeline');

test('scanHarnessHtml finds hidden inputs in the real harness shape', () => {
  const html = `
    <form>
      <input type="hidden" name="_csrf" value="abc">
      <input type="password" name="password">
    </form>
  `;
  const findings = scanHarnessHtml(html);
  assert.ok(findings.some(f => f.pattern_type === 'HIDDEN_INPUT'));
  assert.ok(findings.some(f => f.pattern_type === 'PASSWORD_FIELD'));
});

test('artifactsFromHarnessHtml emits canonical verified-finding artifacts', () => {
  const html = `
    <body>
      <input type="hidden" name="_workflow" value="login-v1">
    </body>
  `;
  const artifacts = artifactsFromHarnessHtml(html, { url: 'http://127.0.0.1:7490/' });
  assert.equal(artifacts.length, 1);
  assert.equal(artifacts[0].artifact_type, 'verified_finding');
  assert.equal(artifacts[0].source.kind, 'synthetic_harness');
  assert.equal(artifacts[0].verification.trust_state, 'demo_only');
});

// ── 11. scanner pipeline ────────────────────────────────────────────────────

console.log('\n11. scanner pipeline');

test('artifactsFromScannerFindings emits canonical scanner artifacts', () => {
  const artifacts = artifactsFromScannerFindings([
    {
      tool: 'mock-dast',
      source_finding_id: 'DAST-1042',
      url: 'https://demo.example/login',
      snippet: '<input type="hidden" name="_workflow" value="login-v1">',
      family: 'hidden_field_leak',
    },
  ]);
  assert.equal(artifacts.length, 1);
  assert.equal(artifacts[0].source.kind, 'scanner_export');
  assert.equal(artifacts[0].verification.trust_state, 'unsupported');
});

test('verifiedScannerArtifacts upgrades hidden-field findings to verified', () => {
  const artifacts = verifiedScannerArtifacts([
    {
      tool: 'mock-dast',
      source_finding_id: 'DAST-1042',
      url: 'https://demo.example/login',
      snippet: '<input type="hidden" name="_workflow" value="login-v1">',
      family: 'hidden_field_leak',
    },
  ]);
  assert.equal(artifacts.length, 1);
  assert.equal(artifacts[0].claim.family, 'HIDDEN_INPUT');
  assert.equal(artifacts[0].verification.trust_state, 'verified');
  assert.equal(artifacts[0].verification.demo_only, false);
});

// -- 12. outbound message actions --------------------------------------------

console.log('\n12. outbound message actions');

test('evaluateOutboundMessagePolicy returns ready_to_send for compliant message', () => {
  const [message] = defaultOutboundMessages();
  const result = evaluateOutboundMessagePolicy(message);
  assert.equal(result.trust_state, 'ready_to_send');
  assert.equal(result.verifier_status, 'policy_passed');
});

test('evaluateOutboundMessagePolicy returns needs_review for noncompliant message', () => {
  const [, message] = defaultOutboundMessages();
  const result = evaluateOutboundMessagePolicy(message);
  assert.equal(result.trust_state, 'needs_review');
  assert.ok(result.reasons.length > 0);
});

test('artifactsFromOutboundMessages emits agent_action artifacts', () => {
  const artifacts = artifactsFromOutboundMessages(defaultOutboundMessages());
  assert.equal(artifacts.length, 2);
  assert.equal(artifacts[0].artifact_type, 'agent_action');
  assert.equal(artifacts[0].verification.trust_state, 'needs_review');
});

test('reviewedOutboundMessageArtifacts emits ready and review states', () => {
  const artifacts = reviewedOutboundMessageArtifacts();
  assert.equal(artifacts.length, 2);
  assert.equal(artifacts[0].verification.trust_state, 'ready_to_send');
  assert.equal(artifacts[1].verification.trust_state, 'needs_review');
});

test('parseMessageDraftFile loads drafts from fixture object shape', () => {
  const filePath = path.join(process.cwd(), 'examples', 'fixtures', 'real_message_drafts.json');
  const drafts = parseMessageDraftFile(filePath);
  assert.equal(drafts.length, 2);
  assert.equal(drafts[0].tool, 'polsia-agent');
  assert.equal(drafts[0].message_id, 'REAL-2001');
});

test('reviewedArtifactsFromDraftFile emits policy-reviewed action artifacts', () => {
  const filePath = path.join(process.cwd(), 'examples', 'fixtures', 'real_message_drafts.json');
  const artifacts = reviewedArtifactsFromDraftFile(filePath);
  assert.equal(artifacts.length, 2);
  assert.equal(artifacts[0].verification.trust_state, 'ready_to_send');
  assert.equal(artifacts[1].verification.trust_state, 'needs_review');
});

test('parseMessageDraftFile also accepts ops queue object shape', () => {
  const filePath = path.join(process.cwd(), 'ops', 'queue', 'outbound_messages.json');
  const drafts = parseMessageDraftFile(filePath);
  assert.equal(drafts.length, 2);
  assert.equal(drafts[0].message_id, 'OPS-MSG-3001');
});

test('runOutboundMessageOpsLoop exports bundle from ops queue', () => {
  const queuePath = path.join(process.cwd(), 'ops', 'queue', 'outbound_messages.json');
  const dir = tmpDir();
  const result = runOutboundMessageOpsLoop(queuePath, dir);
  assert.equal(result.action_count, 2);
  assert.ok(existsSync(result.handoff_path));
});

// -- 12. report renderer -----------------------------------------------------

console.log('\n12. report renderer');

test('renderFindingReport includes summary, verification, and evidence', () => {
  const artifact = adaptHarnessFinding({
    finding_id: 'h-1',
    pattern_type: 'HIDDEN_INPUT',
    raw_string: '<input type="hidden" name="_csrf" value="abc">',
    summary: 'Harness finding normalized for triage.',
  });
  const report = renderFindingReport(artifact);
  assert.ok(report.includes('# Verified Finding: h-1'));
  assert.ok(report.includes('Harness finding normalized for triage.'));
  assert.ok(report.includes('trust_state: demo_only'));
  assert.ok(report.includes('recommended_action: Treat HIDDEN_INPUT as a triage hint'));
  assert.ok(report.includes('snippet:'));
});

test('renderFindingReport includes action section for agent_action artifacts', () => {
  const artifact = adaptOutboundMessageAction({
    message_id: 'MSG-1001',
    recipient: 'owner@customer.example',
    message_body: 'Sent by AI assistant.',
    trust_state: 'ready_to_send',
    verifier_status: 'policy_passed',
    proof_status: 'policy_checked',
    demo_only: true,
  });
  const report = renderFindingReport(artifact);
  assert.ok(report.includes('# Agent Action: message-msg-1001'));
  assert.ok(report.includes('## Action'));
  assert.ok(report.includes('recipient: owner@customer.example'));
});

test('renderFindingReportSet summarizes trust states across artifacts', () => {
  const artifacts = [
    adaptHarnessFinding({ pattern_type: 'HIDDEN_INPUT' }),
    adaptScannerFinding({ family: 'hidden_field_leak', trust_state: 'unsupported' }),
  ];
  const report = renderFindingReportSet(artifacts, { title: 'Demo Report' });
  assert.ok(report.includes('# Demo Report'));
  assert.ok(report.includes('artifact_count: 2'));
  assert.ok(report.includes('demo_only=1'));
  assert.ok(report.includes('handoff_readiness:'));
  assert.ok(report.includes('unsupported=1'));
});

test('buildReportSummary exposes verified finding ids and handoff summary', () => {
  const verifiedArtifact = adaptScannerFinding({
    finding_id: 'scanner-verified-1',
    trust_state: 'verified',
    proof_status: 'generated',
    verifier_status: 'passed',
    demo_only: false,
  });
  const summary = buildReportSummary([verifiedArtifact], { title: 'Summary Report' });
  assert.equal(summary.title, 'Summary Report');
  assert.equal(summary.artifact_count, 1);
  assert.deepEqual(summary.verified_finding_ids, ['scanner-verified-1']);
  assert.ok(summary.handoff_readiness.includes('ready for high-confidence engineering handoff'));
});

test('renderEngineeringHandoff separates ready and pending findings', () => {
  const artifacts = [
    adaptScannerFinding({
      finding_id: 'scanner-ready-1',
      trust_state: 'verified',
      proof_status: 'generated',
      verifier_status: 'passed',
      demo_only: false,
      title: 'Verified hidden input: _workflow',
      url: 'https://demo.example/login',
    }),
    adaptHarnessFinding({
      finding_id: 'h-pending-1',
      pattern_type: 'INLINE_SCRIPT',
    }),
  ];
  const report = renderEngineeringHandoff(artifacts, { title: 'Handoff Report' });
  assert.ok(report.includes('# Handoff Report Engineering Handoff'));
  assert.ok(report.includes('scanner-ready-1: Verified hidden input: _workflow'));
  assert.ok(report.includes('h-pending-1: INLINE_SCRIPT remains demo_only'));
});

test('exportFindingReportSet writes report index, manifest, and per-finding bundles', () => {
  const dir = tmpDir();
  const artifacts = [
    adaptHarnessFinding({
      finding_id: 'h-report-1',
      pattern_type: 'HIDDEN_INPUT',
      raw_string: '<input type="hidden" name="_csrf" value="abc">',
    }),
    adaptScannerFinding({
      tool: 'mock-dast',
      source_finding_id: 'DAST-1042',
      family: 'hidden_field_leak',
    }),
  ];
  const exported = exportFindingReportSet(artifacts, dir, { title: 'Bundle Report' });
  assert.ok(existsSync(exported.handoff_path));
  assert.ok(existsSync(exported.index_path));
  assert.ok(existsSync(exported.manifest_path));
  assert.equal(exported.bundles.length, 2);
  assert.ok(existsSync(exported.bundles[0].report_path));
  assert.ok(existsSync(exported.bundles[0].artifact_path));
  assert.ok(readFileSync(exported.index_path, 'utf-8').includes('# Bundle Report'));
  assert.ok(readFileSync(exported.handoff_path, 'utf-8').includes('## Ready Now'));
  assert.ok(readFileSync(exported.manifest_path, 'utf-8').includes('handoff_readiness'));
});

test('buildDemoPacket writes overview and packet manifest', () => {
  const dir = tmpDir();
  const packet = buildDemoPacket(
    {
      harness: {
        root_dir: path.join(dir, 'harness'),
        handoff_path: path.join(dir, 'harness', 'engineering_handoff.md'),
        index_path: path.join(dir, 'harness', 'index.md'),
        manifest_path: path.join(dir, 'harness', 'manifest.json'),
        summary: {
          handoff_readiness: '1 finding is ready for high-confidence handoff.',
        },
      },
      scanner: {
        root_dir: path.join(dir, 'scanner'),
        handoff_path: path.join(dir, 'scanner', 'engineering_handoff.md'),
        index_path: path.join(dir, 'scanner', 'index.md'),
        manifest_path: path.join(dir, 'scanner', 'manifest.json'),
        summary: {
          handoff_readiness: '2 findings are ready for high-confidence handoff.',
        },
      },
      messages: {
        root_dir: path.join(dir, 'messages'),
        handoff_path: path.join(dir, 'messages', 'engineering_handoff.md'),
        index_path: path.join(dir, 'messages', 'index.md'),
        manifest_path: path.join(dir, 'messages', 'manifest.json'),
        summary: {
          handoff_readiness: '1 action is ready to proceed and 1 needs review.',
        },
      },
    },
    path.join(dir, 'packet')
  );
  assert.ok(existsSync(packet.overview_path));
  assert.ok(existsSync(packet.talk_track_path));
  assert.ok(existsSync(packet.manifest_path));
  assert.ok(readFileSync(packet.overview_path, 'utf-8').includes('# Polsia Demo Packet'));
  assert.ok(readFileSync(packet.talk_track_path, 'utf-8').includes('# Polsia Demo Talk Track'));
  assert.ok(packet.bundles.messages);
  assert.ok(readFileSync(packet.manifest_path, 'utf-8').includes('polsia_demo_packet'));
});

// ── 12. registry ──────────────────────────────────────────────────────────────

console.log('\n12. registry — loadAll and getBaselineForFamily');

test('loadAll with missing files returns empty objects (no crash)', () => {
  const { registry, candidates } = loadAll({
    registryPath:  '/nonexistent/registry.json',
    candidatePath: '/nonexistent/candidate.json',
  });
  assert.deepEqual(registry,   {});
  assert.deepEqual(candidates, {});
});

test('getBaselineForFamily returns entry from registry', () => {
  const reg = { form_workflow_inconsistency: { t_stable_sec_p50: 5.2, t_stable_sec_mad: 0.3 } };
  const entry = getBaselineForFamily('form_workflow_inconsistency', reg);
  assert.equal(entry.t_stable_sec_p50, 5.2);
});

test('getBaselineForFamily returns null for unknown family', () => {
  assert.equal(getBaselineForFamily('not_a_family', {}), null);
});

test('getBaselineForFamily does not reach into candidates', () => {
  // Registry is empty; candidate exists — should not be returned.
  const entry = getBaselineForFamily('hidden_field_leak', {});
  assert.equal(entry, null);
});

// ── 13. consolidation statistics ─────────────────────────────────────────────

console.log('\n13. consolidation — median, mad, tagOutliers');

test('median of odd-length array', () => {
  assert.equal(median([3, 1, 4, 1, 5]), 3);
});

test('median of even-length array is average of two middle values', () => {
  assert.equal(median([1, 3, 5, 7]), 4);
});

test('median of single element', () => {
  assert.equal(median([42]), 42);
});

test('median of empty array returns null', () => {
  assert.equal(median([]), null);
});

test('mad of identical values is 0', () => {
  assert.equal(mad([5, 5, 5, 5]), 0);
});

test('mad of [1,2,3,4,5] = median([1,1,0,1,2]) = 1', () => {
  // median=3, deviations=[2,1,0,1,2], median of deviations=1
  assert.equal(mad([1, 2, 3, 4, 5]), 1);
});

test('mad of empty array returns null', () => {
  assert.equal(mad([]), null);
});

test('tagOutliers: no outliers in tight cluster', () => {
  const tagged = tagOutliers([10, 11, 10, 12, 10]);
  assert.ok(tagged.every(t => !t.outlier));
});

test('tagOutliers: clear outlier is tagged', () => {
  // median=3.5, MAD=1.5, 3*MAD=4.5; |100-3.5|=96.5 >> 4.5
  const tagged = tagOutliers([1, 2, 3, 4, 5, 100]);
  const outliers = tagged.filter(t => t.outlier);
  assert.equal(outliers.length, 1);
  assert.equal(outliers[0].value, 100);
});

test('tagOutliers: preserves original order', () => {
  const vals   = [5, 1, 3, 2, 4];
  const tagged = tagOutliers(vals);
  assert.deepEqual(tagged.map(t => t.value), vals);
});

test('tagOutliers of empty array returns []', () => {
  assert.deepEqual(tagOutliers([]), []);
});

// ── Summary ───────────────────────────────────────────────────────────────────

console.log(`\n${'─'.repeat(50)}`);
console.log(`Tests: ${passed + failed}  Passed: ${passed}  Failed: ${failed}`);
if (failed > 0) {
  process.exit(1);
}
