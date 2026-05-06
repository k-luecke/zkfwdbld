// seer_eval/score.mjs — Run scoring, Tier 1–4.
// No side effects. Pure functions only.

export const LAMBDA = 2;          // retry penalty weight in efficiency formula
export const CONFLICT_THRESHOLD = 0.10;

// Tier 1 base outcome values.
const OUTCOME_BASE = { SUCCESS: 1.0, SAFE_ABORT: 0.4, FAIL: 0.0 };

// Composite weights must sum to 1.
const W = { outcome: 0.40, efficiency: 0.25, discipline: 0.25, adaptation: 0.10 };

/**
 * Score a completed run.
 *
 * @param {object} metrics         - from the run record
 * @param {object} cognitiveState  - from the run record
 * @param {object} adaptation      - from the run record
 * @param {object} flags           - from the run record
 * @param {object|null} baseline   - family entry from family_baseline_registry.json, or null
 * @returns {{ breakdown: object, composite: number }}
 */
export function scoreRun(metrics, cognitiveState, adaptation, flags, baseline = null) {
  const m   = metrics        ?? {};
  const cog = cognitiveState ?? {};
  const adp = adaptation     ?? {};
  const fl  = flags          ?? {};

  // Transport leaks → total score is zero, no further calculation.
  if (cog.transport_leaks === true) {
    return {
      breakdown: {
        transport_leak_override: true,
        outcome: 0, efficiency: 0, discipline: 0, adaptation: 0,
      },
      composite: 0,
    };
  }

  // ── Tier 1: Outcome ────────────────────────────────────────────────────────
  // Absent outcome defaults to FAIL (sparse-record ergonomic, see buildRecord).
  // Unknown keys throw — silent 0 would let typos masquerade as legitimate FAILs.
  const outcomeKey = m.outcome ?? 'FAIL';
  if (!Object.prototype.hasOwnProperty.call(OUTCOME_BASE, outcomeKey)) {
    throw new Error(`scoreRun: unknown outcome key ${JSON.stringify(outcomeKey)}; expected one of ${Object.keys(OUTCOME_BASE).join(', ')}`);
  }
  let O = OUTCOME_BASE[outcomeKey];

  const bannedViolations = m.banned_violations ?? 0;
  if (bannedViolations > 0) O = O * 0.5;   // halve outcome contribution

  // ── Tier 2: Efficiency ─────────────────────────────────────────────────────
  const S_T     = m.successful_transitions ?? 0;
  const A_total = m.total_actions          ?? 0;
  const R       = m.retries                ?? 0;
  const denom   = A_total + LAMBDA * R;
  const E       = denom > 0 ? S_T / denom : (S_T > 0 ? 1.0 : 0.0);

  // ── Tier 3: Discipline ─────────────────────────────────────────────────────
  const V_b     = bannedViolations;
  const cycles  = m.obs_cycles_to_stability ?? 0;
  const flicker = m.flicker_events          ?? 0;
  const F_p     = cycles > 0 ? flicker / cycles : 0;
  const D       = Math.max(0, 1 - 0.2 * V_b - 0.1 * F_p);

  // ── Tier 4: Adaptation (only when baseline exists) ─────────────────────────
  let A = 0;
  let adaptationSource = 'none';
  if (baseline && typeof baseline.t_stable_sec_p50 === 'number' && baseline.t_stable_sec_p50 > 0) {
    const delta = adp.t_stable_delta ?? 0;
    // Negative delta = faster than baseline = positive adaptation credit.
    const rawBonus = -(delta / baseline.t_stable_sec_p50);
    A = Math.min(1.0, Math.max(0, rawBonus));
    adaptationSource = 'family_baseline_registry';
  }

  // ── Composite ──────────────────────────────────────────────────────────────
  const composite = W.outcome * O + W.efficiency * E + W.discipline * D + W.adaptation * A;

  return {
    breakdown: {
      transport_leak_override: false,
      outcome:           { raw: OUTCOME_BASE[outcomeKey], after_ban_penalty: O, weight: W.outcome },
      efficiency:        { S_T, A_total, R, lambda: LAMBDA, score: E, weight: W.efficiency },
      discipline:        { V_b, F_p, score: D, weight: W.discipline },
      adaptation:        { delta: adp.t_stable_delta ?? null, score: A, source: adaptationSource, weight: W.adaptation },
    },
    composite: Math.round(composite * 10000) / 10000,  // 4 dp, no float noise
  };
}
