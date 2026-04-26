// seer_eval/scanner_pipeline.mjs — normalize mocked scanner exports into verified findings.

import { adaptScannerFinding } from './adapters.mjs';
import { encodeHiddenInputClaim } from './claim_encoder.mjs';
import { proveAndVerify } from './prover_bridge.mjs';

export function artifactsFromScannerFindings(findings = []) {
  return findings.map(finding => adaptScannerFinding(finding));
}

export function verifiedScannerArtifacts(findings = []) {
  return artifactsFromScannerFindings(findings).map(artifact => {
    if (artifact.claim.family !== 'hidden_field_leak') {
      return artifact;
    }

    const encoded = encodeHiddenInputClaim({
      raw_string: artifact.evidence.snippet,
      url: artifact.target.url,
      workflow_id: artifact.target.workflow_id,
      source_kind: artifact.source.kind,
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
          `Scanner finding encoded as ${encoded.category}.`,
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
          ? 'Scanner finding encoded and verified through the Rust proof bridge.'
          : 'Scanner finding claim encoding attempted but verification did not pass.',
    };
  });
}

export function defaultScannerFindings() {
  return [
    {
      tool: 'mock-dast',
      source_finding_id: 'DAST-1042',
      url: 'https://demo.example/login',
      snippet: '<input type="hidden" name="_workflow" value="login-v1">',
      family: 'hidden_field_leak',
      severity: 'medium',
      confidence: 0.74,
      rule_id: 'MOCK-HFL-001',
    },
    {
      tool: 'mock-dast',
      source_finding_id: 'DAST-1043',
      url: 'https://demo.example/login',
      snippet: '<input type="hidden" name="_session" value="00000000-0000-0000-0000-000000000000">',
      family: 'hidden_field_leak',
      severity: 'high',
      confidence: 0.82,
      rule_id: 'MOCK-HFL-002',
    },
  ];
}
