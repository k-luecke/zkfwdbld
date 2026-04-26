// seer_eval/audit.mjs — Per-run audit record writer.
//
// Writes two outputs per run:
//   1. seer_runs.jsonl       — append-only log; one JSON line per run.
//   2. seer_audit_record.json — pretty-printed snapshot of the latest run.
//
// Guarantees:
//   - No partial file writes (tmp+rename for audit record).
//   - appendFileSync for JSONL (single write; atomic at OS syscall level).
//   - All fields are null-safe: missing input keys → null in output.

import { writeFileSync, appendFileSync, renameSync } from 'fs';
import path from 'path';

/**
 * Build a normalised run record from raw inputs.
 * All fields are present; missing values become null.
 *
 * @param {string}      runId
 * @param {string}      target           - URL or page identifier
 * @param {object|null} metrics
 * @param {object|null} cognitiveState
 * @param {object|null} adaptation
 * @param {object|null} flags
 * @returns {object}
 */
export function buildRecord(runId, target, metrics, cognitiveState, adaptation, flags) {
  const m   = metrics        ?? {};
  const cog = cognitiveState ?? {};
  const adp = adaptation     ?? {};
  const fl  = flags          ?? {};

  return {
    run_id:    runId   ?? null,
    target:    target  ?? null,
    ts:        new Date().toISOString(),

    metrics: {
      outcome:                    m.outcome                    ?? null,
      successful_transitions:     m.successful_transitions     ?? null,
      total_actions:              m.total_actions              ?? null,
      retries:                    m.retries                    ?? null,
      banned_violations:          m.banned_violations          ?? null,
      obs_cycles_to_stability:    m.obs_cycles_to_stability    ?? null,
      flicker_events:             m.flicker_events             ?? null,
    },

    cognitive_state: {
      active_pattern:             cog.active_pattern           ?? null,
      state:                      cog.state                    ?? null,
      transport_leaks:            cog.transport_leaks          ?? null,
      candidates_above_threshold: cog.candidates_above_threshold ?? null,
    },

    adaptation: {
      t_stable_delta:             adp.t_stable_delta           ?? null,
      family:                     adp.family                   ?? null,
      baseline_source:            adp.baseline_source          ?? null,
    },

    flags: {
      deep_observation:           fl.deep_observation          ?? null,
      unknown_pattern:            fl.unknown_pattern           ?? null,
      conflict_detected:          fl.conflict_detected         ?? null,
    },
  };
}

/**
 * Persist a run record to disk.
 *
 * @param {object} record          - from buildRecord()
 * @param {object} paths
 * @param {string} paths.runsPath  - path to seer_runs.jsonl
 * @param {string} paths.auditPath - path to seer_audit_record.json
 */
export function appendRun(record, { runsPath, auditPath }) {
  // 1. Append one compact JSON line to the JSONL log.
  //    appendFileSync is a single write syscall — safe for this use.
  appendFileSync(runsPath, JSON.stringify(record) + '\n', 'utf-8');

  // 2. Atomically overwrite the pretty-printed snapshot.
  const tmp = auditPath + '.tmp';
  writeFileSync(tmp, JSON.stringify(record, null, 2) + '\n', 'utf-8');
  renameSync(tmp, auditPath);
}
