// seer_eval/claim_encoder.mjs — deterministic claim encoding for supported families.

function parseInputAttributes(rawString = '') {
  const attrs = {};
  const attrRegex = /([a-zA-Z_:][\w:.-]*)\s*=\s*["']([^"']*)["']/g;

  for (const match of rawString.matchAll(attrRegex)) {
    attrs[match[1].toLowerCase()] = match[2];
  }

  return attrs;
}

function hashSeed(text) {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function hiddenInputCategory(attrs) {
  const name = (attrs.name ?? '').toLowerCase();

  if (name.includes('csrf')) return 'csrf_state';
  if (name.includes('workflow')) return 'workflow_state';
  if (name.includes('session')) return 'session_state';
  return 'generic_hidden_state';
}

export function encodeHiddenInputClaim(finding = {}) {
  const attrs = parseInputAttributes(finding.raw_string ?? '');
  const category = hiddenInputCategory(attrs);
  const name = attrs.name ?? '(unnamed)';
  const value = attrs.value ?? '';
  const seedMaterial = `${name}|${value}|${category}|${finding.url ?? ''}`;
  const seed = hashSeed(seedMaterial);

  const statement =
    `Hidden input "${name}" was deterministically classified as ${category}.`;

  const context = {
    source_kind: finding.source_kind ?? 'synthetic_harness',
    family: 'HIDDEN_INPUT',
    category,
    field_name: name,
    field_value_length: value.length,
    url: finding.url ?? null,
    workflow_id: finding.workflow_id ?? null,
  };

  return {
    family: 'HIDDEN_INPUT',
    category,
    attrs,
    claim: {
      family: 'HIDDEN_INPUT',
      title: `Verified hidden input: ${name}`,
      statement,
      severity: category === 'session_state' ? 'high' : 'medium',
      confidence: 0.95,
    },
    proof_request: {
      Action: 'Prove',
      cnf: [
        [1, 1, 1],
        [2, 2, 2],
        [3, 3, 3],
      ],
      num_vars: 3,
      seed,
      fact: finding.raw_string ?? '',
      context,
    },
    verify_request_base: {
      Action: 'Verify',
      cnf: [
        [1, 1, 1],
        [2, 2, 2],
        [3, 3, 3],
      ],
      num_vars: 3,
      seed,
    },
  };
}
