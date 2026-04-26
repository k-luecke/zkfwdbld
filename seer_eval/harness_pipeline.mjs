// seer_eval/harness_pipeline.mjs — scan real harness HTML into verified findings.

import { readFileSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

import { adaptHarnessFinding } from './adapters.mjs';
import { encodeHiddenInputClaim } from './claim_encoder.mjs';
import { proveAndVerify } from './prover_bridge.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const HARNESS_PATTERN_RULES = [
  { name: 'HIDDEN_INPUT', regex: /<input[^>]+type\s*=\s*["']?hidden[^>]*>/gi },
  { name: 'JS_COMMENT', regex: /<!--[\s\S]*?-->/g },
  { name: 'INLINE_SCRIPT', regex: /<script[^>]*>[\s\S]+?<\/script>/gi },
  { name: 'MAILTO_LEAK', regex: /mailto:[\w.+-]+@[\w.-]+/gi },
  { name: 'NONSTANDARD_HDR', regex: /(?:^|\n)X-[\w-]+:\s*.+$/gmi },
  { name: 'PASSWORD_FIELD', regex: /<input[^>]+name\s*=\s*["']?passw[^>]*>/gi },
];

function findingIdFor(patternType, offset) {
  return `harness-${patternType.toLowerCase()}-${offset}`;
}

export function scanHarnessHtml(html) {
  const findings = [];

  for (const rule of HARNESS_PATTERN_RULES) {
    for (const match of html.matchAll(rule.regex)) {
      const raw = match[0];
      const offset = match.index ?? null;
      findings.push({
        finding_id: findingIdFor(rule.name, offset ?? 0),
        pattern_type: rule.name,
        raw_string: raw.slice(0, 256),
        offset,
        locator: 'html:body',
      });
    }
  }

  return findings.sort((a, b) => (a.offset ?? 0) - (b.offset ?? 0));
}

export function artifactsFromHarnessHtml(html, options = {}) {
  const url = options.url ?? 'http://127.0.0.1:7490/';
  const level = options.level ?? '0';
  const workflowId = options.workflow_id ?? 'phase0_form_workflow';
  const encoderMode = options.encoder_mode ?? 'demo';
  const includePatterns = options.include_patterns ?? null;

  return scanHarnessHtml(html)
    .filter(finding => !includePatterns || includePatterns.includes(finding.pattern_type))
    .map(finding =>
    adaptHarnessFinding({
      ...finding,
      url,
      level,
      workflow_id: workflowId,
      encoder_mode: encoderMode,
    })
  );
}

export function artifactsFromHarnessFile(filePath, options = {}) {
  const html = readFileSync(filePath, 'utf-8');
  return artifactsFromHarnessHtml(html, options);
}

export function defaultHarnessArtifacts(options = {}) {
  const harnessPath =
    options.filePath ??
    path.join(__dirname, '..', 'harness', 'phase0_form_workflow.html');

  return artifactsFromHarnessFile(harnessPath, {
    include_patterns: ['HIDDEN_INPUT', 'PASSWORD_FIELD', 'INLINE_SCRIPT'],
    ...options,
  });
}

export function verifiedHarnessArtifacts(options = {}) {
  return defaultHarnessArtifacts(options).map(artifact => {
    if (artifact.claim.family !== 'HIDDEN_INPUT') {
      return artifact;
    }

    const encoded = encodeHiddenInputClaim({
      raw_string: artifact.evidence.snippet,
      url: artifact.target.url,
      workflow_id: artifact.target.workflow_id,
    });
    const result = proveAndVerify(encoded);

    return {
      ...artifact,
      claim: encoded.claim,
      trace: {
        ...artifact.trace,
        proof_input: {
          mode: 'supported',
          source_family: encoded.family,
          category: encoded.category,
          seed: encoded.proof_request.seed,
          num_vars: encoded.proof_request.num_vars,
          cnf: encoded.proof_request.cnf,
        },
        transformation_notes: [
          ...artifact.trace.transformation_notes,
          `Hidden-input claim encoded as ${encoded.category}.`,
          'Rust proof bridge executed local prove and verify flow.',
        ],
      },
      verification: {
        trust_state: result.trust_state,
        proof_status: result.prove?.success ? 'generated' : 'error',
        verifier_status: result.verifier_status,
        satisfiable: result.verify?.satisfiable ?? result.prove?.satisfiable ?? null,
        demo_only: false,
        artifact_ref: null,
      },
      summary:
        result.trust_state === 'verified'
          ? 'Hidden input encoded and verified through the Rust proof bridge.'
          : 'Hidden input claim encoding attempted but verification did not pass.',
    };
  });
}
