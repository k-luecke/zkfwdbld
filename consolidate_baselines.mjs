// consolidate_baselines.mjs — Derive per-family baseline statistics from run logs.
//
// Reads:  seer_runs.jsonl
// Writes: family_baseline_candidate.json  (never auto-promoted to registry)
//
// Stats per family (robust, outlier-resistant):
//   - t_stable_sec_p50:  median of t_stable_sec values
//   - t_stable_sec_mad:  MAD (median absolute deviation)
//   - n:                 sample count (all runs, incl. outliers)
//   - n_outliers:        count of outlier-tagged runs
//
// Outlier rule: |x - median| > 3 * MAD  (tag only; never deleted from input)
//
// Usage: node consolidate_baselines.mjs [runs.jsonl] [candidate.json]

import { readFileSync, writeFileSync, renameSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── Pure statistics helpers (exported for tests) ──────────────────────────────

/**
 * Compute the median of a numeric array.  Returns null for empty input.
 * @param {number[]} values
 * @returns {number|null}
 */
export function median(values) {
  if (!values || values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * Compute the Median Absolute Deviation (MAD).  Returns null for empty input.
 * MAD = median(|x_i - median(x)|)
 * @param {number[]} values
 * @returns {number|null}
 */
export function mad(values) {
  if (!values || values.length === 0) return null;
  const med = median(values);
  const deviations = values.map(v => Math.abs(v - med));
  return median(deviations);
}

/**
 * Tag each value as an outlier if |x - median| > 3 * MAD.
 * Returns an array of { value, outlier } objects in original order.
 *
 * @param {number[]} values
 * @returns {Array<{ value: number, outlier: boolean }>}
 */
export function tagOutliers(values) {
  if (!values || values.length === 0) return [];
  const med = median(values);
  const m   = mad(values);
  // When MAD is zero all points that equal the median are inliers;
  // strict inequality keeps the rule consistent and avoids false positives.
  return values.map(v => ({
    value:   v,
    outlier: m > 0 && Math.abs(v - med) > 3 * m,
  }));
}

// ── Consolidation logic ───────────────────────────────────────────────────────

/**
 * Parse seer_runs.jsonl lines.  Skips blank lines and parse errors.
 * Returns { runs, skipped } so the caller can surface a count of malformed
 * lines (audit L-8: silent drops would let a corrupted run log degrade
 * baselines invisibly).
 *
 * @param {string} raw
 * @returns {{ runs: object[], skipped: number }}
 */
function parseRunsJsonl(raw) {
  const runs = [];
  let skipped = 0;
  for (const line of raw.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      runs.push(JSON.parse(trimmed));
    } catch {
      skipped += 1;
    }
  }
  return { runs, skipped };
}

/**
 * Group runs by pattern family.
 * A run contributes if it has adaptation.family and adaptation.t_stable_delta is numeric.
 *
 * @param {object[]} runs
 * @returns {Map<string, number[]>}  family → array of t_stable values
 */
function groupByFamily(runs) {
  const groups = new Map();
  for (const run of runs) {
    const family = run?.adaptation?.family;
    const delta  = run?.adaptation?.t_stable_delta;
    if (typeof family !== 'string' || family.trim() === '') continue;
    if (typeof delta  !== 'number' || !isFinite(delta))    continue;
    if (!groups.has(family)) groups.set(family, []);
    groups.get(family).push(delta);
  }
  return groups;
}

/**
 * Build the candidate registry object from grouped data.
 * @param {Map<string, number[]>} groups
 * @returns {object}  family → baseline entry
 */
function buildCandidates(groups) {
  const result = {};
  for (const [family, values] of groups) {
    const tagged     = tagOutliers(values);
    const inliers    = tagged.filter(t => !t.outlier).map(t => t.value);
    const statValues = inliers.length > 0 ? inliers : values; // fall back if all outliers

    result[family] = {
      t_stable_sec_p50: median(statValues),
      t_stable_sec_mad: mad(statValues),
      n:                values.length,
      n_outliers:       tagged.filter(t => t.outlier).length,
      generated_at:     new Date().toISOString(),
    };
  }
  return result;
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  const runsPath     = process.argv[2] ?? path.join(__dirname, 'seer_runs.jsonl');
  const candidatePath = process.argv[3] ?? path.join(__dirname, 'family_baseline_candidate.json');

  let raw;
  try {
    raw = readFileSync(runsPath, 'utf-8');
  } catch (e) {
    console.error(`Cannot read ${runsPath}: ${e.message}`);
    process.exit(1);
  }

  const { runs, skipped } = parseRunsJsonl(raw);
  if (skipped > 0) {
    // Audit L-8 (#32): emit a warning so a corrupted JSONL does not silently
    // produce a degraded baseline. Tests / CI can grep for this prefix.
    console.warn(
      `consolidate_baselines: WARNING — skipped ${skipped} malformed JSONL line(s) in ${runsPath}`
    );
  }
  const groups     = groupByFamily(runs);
  const candidates = buildCandidates(groups);

  const families = Object.keys(candidates);
  console.log(`Processed ${runs.length} run(s), ${families.length} family(ies): ${families.join(', ') || '(none)'}`);

  const tmp = candidatePath + '.tmp';
  writeFileSync(tmp, JSON.stringify(candidates, null, 2) + '\n', 'utf-8');
  renameSync(tmp, candidatePath);
  console.log(`Wrote candidate baseline → ${candidatePath}`);
}

// Only run main() when invoked directly (not when imported by tests).
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch(e => {
    console.error('FATAL:', e.message);
    process.exit(1);
  });
}
