import { adaptHarnessFinding, adaptScannerFinding, adaptAgentFinding } from '../seer_eval/adapters.mjs';

const artifacts = [
  adaptHarnessFinding({
    pattern_type: 'HIDDEN_INPUT',
    raw_string: '<input type="hidden" name="_csrf" value="phase0-static-token-aabbccdd">',
    offset: 512,
    level: '0',
    encoder_mode: 'demo',
  }),
  adaptScannerFinding({
    tool: 'mock-dast',
    source_finding_id: 'DAST-1042',
    url: 'https://demo.example/login',
    snippet: '<input type="hidden" name="workflow" value="login-v1">',
    severity: 'medium',
    confidence: 0.74,
  }),
  adaptAgentFinding({
    tool: 'mock-browser-agent',
    source_finding_id: 'AGENT-77',
    url: 'https://demo.example/login',
    workflow_id: 'login-sequence',
    snippet: 'Submit button enabled after hidden workflow field becomes present.',
    rationale: 'Observed hidden state transition before successful authentication step.',
  }),
];

console.log(JSON.stringify(artifacts, null, 2));
