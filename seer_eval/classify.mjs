// seer_eval/classify.mjs — Multi-label classification control layer.
//
// Rules:
//   - classification returns multiple candidate families with confidence
//   - action layer activates only one pattern
//   - all candidates above threshold still contribute banned-inference union
//   - if |top1 - top2| < conflict_threshold → DEEP_OBSERVATION (no active pattern)
//   - if no candidate above threshold → UNKNOWN_PATTERN

// Per-family banned inferences.  Extend as new families are observed.
export const PATTERN_DEFINITIONS = {
  form_workflow_inconsistency: {
    banned_semantic: [
      'assume_auth_bypass',
      'skip_form_validation',
      'assume_session_valid',
    ],
    banned_action: [
      'submit_without_observation',
      'skip_hidden_field_scan',
    ],
  },
  hidden_field_leak: {
    banned_semantic: [
      'ignore_hidden_fields',
      'trust_form_defaults',
    ],
    banned_action: [
      'skip_field_enumeration',
    ],
  },
  js_state_injection: {
    banned_semantic: [
      'assume_dom_static',
      'skip_script_analysis',
    ],
    banned_action: [
      'interact_before_stabilization',
    ],
  },
  inline_script_hint: {
    banned_semantic: [
      'ignore_js_comments',
      'assume_no_hardcoded_values',
    ],
    banned_action: [
      'skip_source_inspection',
    ],
  },
  header_information_disclosure: {
    banned_semantic: [
      'assume_standard_stack',
      'ignore_server_headers',
    ],
    banned_action: [
      'skip_header_enumeration',
    ],
  },
  mailto_credential_leak: {
    banned_semantic: [
      'ignore_mailto_links',
      'assume_email_non_functional',
    ],
    banned_action: [
      'skip_contact_enumeration',
    ],
  },
  unknown_pattern: {
    banned_semantic: [],
    banned_action:   [],
  },
};

/**
 * Classify a set of pattern candidates into an active pattern and banned-inference union.
 *
 * @param {Array<{pattern: string, confidence: number}>} candidates
 * @param {object} options
 * @param {number} [options.conflictThreshold=0.10]   - |top1-top2| below this → DEEP_OBSERVATION
 * @param {number} [options.activationThreshold=0.30] - minimum confidence to activate a pattern
 * @returns {{
 *   activePattern: string|null,
 *   state: 'OBSERVING'|'DEEP_OBSERVATION'|'UNKNOWN_PATTERN',
 *   candidatesAboveThreshold: Array,
 *   bannedSemanticInferences: string[],
 *   bannedActionInferences: string[],
 * }}
 */
export function classify(candidates, options = {}) {
  const conflictThreshold    = options.conflictThreshold    ?? 0.10;
  const activationThreshold  = options.activationThreshold  ?? 0.30;

  const sorted = [...(candidates ?? [])].sort((a, b) => b.confidence - a.confidence);

  const top1 = sorted[0];
  const top2 = sorted[1];

  let activePattern = null;
  let state;

  if (!top1 || top1.confidence < activationThreshold) {
    activePattern = 'UNKNOWN_PATTERN';
    state = 'UNKNOWN_PATTERN';
  } else if (top2 && (top1.confidence - top2.confidence) < conflictThreshold) {
    activePattern = null;   // conflict — cannot commit to one pattern
    state = 'DEEP_OBSERVATION';
  } else {
    activePattern = top1.pattern;
    state = 'OBSERVING';
  }

  // All candidates at or above threshold contribute to the banned-inference union.
  const candidatesAboveThreshold = sorted.filter(c => c.confidence >= activationThreshold);

  const bannedSemantic = new Set();
  const bannedAction   = new Set();

  for (const c of candidatesAboveThreshold) {
    const def = PATTERN_DEFINITIONS[c.pattern] ?? PATTERN_DEFINITIONS.unknown_pattern;
    for (const b of def.banned_semantic) bannedSemantic.add(b);
    for (const b of def.banned_action)   bannedAction.add(b);
  }

  return {
    activePattern,
    state,
    candidatesAboveThreshold,
    bannedSemanticInferences: [...bannedSemantic].sort(),
    bannedActionInferences:   [...bannedAction].sort(),
  };
}
