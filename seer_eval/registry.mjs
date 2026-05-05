// seer_eval/registry.mjs — Baseline registry loader.
//
// Separates two sources:
//   - family_baseline_registry.json   (promoted, authoritative baselines)
//   - family_baseline_candidate.json  (pending consolidation output, not yet promoted)
//
// getBaselineForFamily() returns ONLY from the registry.
// Candidates are accessible separately for inspection and promotion workflows.
//
// Both files are optional; missing files return empty maps, not errors.

import { readFileSync } from 'fs';

/**
 * Load a JSON file.  Returns null if the file is missing or unparseable.
 * @param {string} filePath
 * @returns {object|null}
 */
function loadJson(filePath) {
  try {
    return JSON.parse(readFileSync(filePath, 'utf-8'));
  } catch (err) {
    // ENOENT (missing file) is expected and silent; any other error
    // (parse failure, permission denied, etc.) is a config bug worth
    // surfacing so the caller doesn't silently degrade to empty registry.
    if (err.code !== 'ENOENT') {
      console.warn(`[registry] failed to load ${filePath}: ${err.message}`);
    }
    return null;
  }
}

/**
 * Load both the registry and candidate files.
 *
 * @param {object} paths
 * @param {string} paths.registryPath   - path to family_baseline_registry.json
 * @param {string} paths.candidatePath  - path to family_baseline_candidate.json
 * @returns {{ registry: object, candidates: object }}
 */
export function loadAll({ registryPath, candidatePath }) {
  return {
    registry:   loadJson(registryPath)  ?? {},
    candidates: loadJson(candidatePath) ?? {},
  };
}

/**
 * Return the authoritative baseline for a pattern family.
 * Returns null if the family has no promoted entry.
 *
 * @param {string} family
 * @param {object} registry  - from loadAll().registry
 * @returns {object|null}
 */
export function getBaselineForFamily(family, registry) {
  return registry[family] ?? null;
}
