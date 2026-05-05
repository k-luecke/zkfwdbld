// seer_eval/claim_encoder.mjs — deterministic claim encoding for supported families.

function parseInputAttributes(rawString = '') {
  const attrs = {};
  const attrRegex = /([a-zA-Z_:][\w:.-]*)\s*=\s*["']([^"']*)["']/g;

  for (const match of rawString.matchAll(attrRegex)) {
    attrs[match[1].toLowerCase()] = match[2];
  }

  return attrs;
}

// FNV-1a 32-bit, byte-accurate over UTF-8. Mirrored in Lua (agent.lua) so the
// AOS encoder and the Node encoder produce the same CNF for the same fact.
function fnv1a32(text) {
  const buf = Buffer.from(text || '', 'utf8');
  let hash = 2166136261;
  for (let i = 0; i < buf.length; i++) {
    hash ^= buf[i];
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

// Derive a 24-variable / 8-clause 3-SAT instance whose polarities are
// determined by FNV-1a(fact). Different facts yield different CNFs (binding
// the proof to finding identity), and the all-1 / all-0 / hash-driven
// witness is always satisfying so the prover terminates. See
// docs/proof_contract.md for the relationship between this encoder and the
// production data-binding encoder.
function deriveCnfFromFact(fact) {
  const polarityHash = fnv1a32(fact ?? '');
  const seedHash = fnv1a32((fact ?? '') + '|cnf');
  const cnf = [];
  for (let j = 0; j < 8; j++) {
    const clause = [];
    for (let k = 0; k < 3; k++) {
      const bitIdx = 3 * j + k;
      const bit = (polarityHash >>> bitIdx) & 1;
      const v = 3 * j + k + 1;
      clause.push(bit === 1 ? v : -v);
    }
    cnf.push(clause);
  }
  return { cnf, num_vars: 24, seed: seedHash };
}

function hiddenInputCategory(attrs) {
  const name = (attrs.name ?? '').toLowerCase();

  if (name.includes('csrf')) return 'csrf_state';
  if (name.includes('workflow')) return 'workflow_state';
  if (name.includes('session')) return 'session_state';
  return 'generic_hidden_state';
}

export function encodeHiddenInputClaim(finding = {}) {
  const fact = finding.raw_string ?? '';
  const attrs = parseInputAttributes(fact);
  const category = hiddenInputCategory(attrs);
  const name = attrs.name ?? '(unnamed)';
  const value = attrs.value ?? '';
  const { cnf, num_vars, seed } = deriveCnfFromFact(fact);

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
      cnf,
      num_vars,
      seed,
      fact,
      context,
    },
    verify_request_base: {
      Action: 'Verify',
      cnf,
      num_vars,
      seed,
    },
  };
}

// Exported for cross-encoder tests. agent.lua mirrors fnv1a32 and
// derive_cnf_from_fact in pure Lua; the two implementations must match
// byte-for-byte.
export { fnv1a32, deriveCnfFromFact };
