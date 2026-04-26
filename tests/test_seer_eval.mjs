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

// ── 9. registry ───────────────────────────────────────────────────────────────

console.log('\n9. registry — loadAll and getBaselineForFamily');

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

// ── 10. consolidation statistics ─────────────────────────────────────────────

console.log('\n10. consolidation — median, mad, tagOutliers');

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
