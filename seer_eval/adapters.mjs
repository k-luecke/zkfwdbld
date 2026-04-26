// seer_eval/adapters.mjs — source adapters for zkfwdbld trust-layer demos.

import { buildAgentActionArtifact, buildFindingArtifact } from './finding_artifact.mjs';

function makeId(prefix, suffix) {
  return `${prefix}-${suffix}`;
}

function slug(value, fallback) {
  const normalized = String(value ?? fallback)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return normalized || fallback;
}

export function adaptHarnessFinding(finding = {}) {
  const family = finding.pattern_type ?? 'unknown_pattern';
  return buildFindingArtifact({
    finding_id: finding.finding_id ?? makeId('harness', family.toLowerCase()),
    source: {
      tool: 'zkfwdbld-harness',
      kind: 'synthetic_harness',
      finding_id: finding.finding_id ?? null,
      event_id: finding.event_id ?? null,
    },
    target: {
      url: finding.url ?? 'http://127.0.0.1:7490/',
      workflow_id: finding.workflow_id ?? 'phase0_form_workflow',
    },
    claim: {
      family,
      title: 'Hidden field detected in controlled workflow',
      statement: `A ${family} finding was extracted from the controlled workflow harness.`,
      severity: 'medium',
      confidence: 0.9,
    },
    evidence: {
      snippet: finding.raw_string ?? null,
      offset: finding.offset ?? null,
      locator: finding.locator ?? 'html:body',
      metadata: { level: finding.level ?? null },
    },
    trace: {
      adapter: 'harness',
      proof_input: {
        mode: finding.encoder_mode ?? 'demo',
        source_family: family,
      },
      transformation_notes: [
        'Finding originated from synthetic harness input.',
        'Pattern mapped directly from DOM scanner output.',
      ],
    },
    verification: {
      trust_state: finding.trust_state ?? 'demo_only',
      proof_status: finding.proof_status ?? 'generated',
      verifier_status: finding.verifier_status ?? 'not_run',
      satisfiable: finding.satisfiable ?? true,
      demo_only: finding.demo_only ?? true,
      artifact_ref: finding.artifact_ref ?? null,
    },
    summary: finding.summary ?? 'Synthetic harness finding normalized into verified-finding artifact.',
  });
}

export function adaptScannerFinding(finding = {}) {
  return buildFindingArtifact({
    finding_id:
      finding.finding_id ??
      makeId('scanner', slug(finding.source_finding_id ?? finding.rule_id ?? finding.family, 'finding')),
    source: {
      tool: finding.tool ?? 'mock-sast',
      kind: 'scanner_export',
      finding_id: finding.source_finding_id ?? finding.finding_id ?? null,
      event_id: finding.event_id ?? null,
    },
    target: {
      url: finding.url ?? null,
      asset: finding.asset ?? 'web-app',
    },
    claim: {
      family: finding.family ?? 'hidden_field_leak',
      title: finding.title ?? 'Possible hidden field leak',
      statement: finding.statement ?? 'Scanner reported a hidden field that may expose workflow state or credentials.',
      severity: finding.severity ?? 'medium',
      confidence: finding.confidence ?? 0.72,
    },
    evidence: {
      snippet: finding.snippet ?? null,
      offset: finding.offset ?? null,
      locator: finding.locator ?? null,
      metadata: {
        rule_id: finding.rule_id ?? 'MOCK-HFL-001',
        source_export_version: finding.source_export_version ?? 'mock-1',
      },
    },
    trace: {
      adapter: 'scanner',
      proof_input: {
        mode: finding.encoder_mode ?? 'unsupported',
        source_family: finding.family ?? 'hidden_field_leak',
      },
      transformation_notes: [
        'Scanner export converted into canonical claim fields.',
        'Original source metadata preserved for triage and traceability.',
      ],
    },
    verification: {
      trust_state: finding.trust_state ?? 'unsupported',
      proof_status: finding.proof_status ?? 'not_attempted',
      verifier_status: finding.verifier_status ?? 'not_run',
      satisfiable: finding.satisfiable ?? null,
      demo_only: finding.demo_only ?? false,
      artifact_ref: finding.artifact_ref ?? null,
    },
    summary: finding.summary ?? 'Mock scanner finding wrapped with trace metadata.',
  });
}

export function adaptAgentFinding(finding = {}) {
  return buildFindingArtifact({
    finding_id: finding.finding_id ?? makeId('agent', 'workflow-anomaly'),
    source: {
      tool: finding.tool ?? 'mock-agent',
      kind: 'agent_output',
      finding_id: finding.source_finding_id ?? finding.finding_id ?? null,
      event_id: finding.event_id ?? null,
    },
    target: {
      url: finding.url ?? null,
      workflow_id: finding.workflow_id ?? null,
      asset: finding.asset ?? 'web-app',
    },
    claim: {
      family: finding.family ?? 'form_workflow_inconsistency',
      title: finding.title ?? 'Agent observed workflow inconsistency',
      statement: finding.statement ?? 'Agent observed a workflow anomaly that may indicate exploitable hidden state.',
      severity: finding.severity ?? 'high',
      confidence: finding.confidence ?? 0.81,
    },
    evidence: {
      snippet: finding.snippet ?? null,
      offset: finding.offset ?? null,
      locator: finding.locator ?? null,
      metadata: {
        model: finding.model ?? 'mock-agent-v1',
        rationale: finding.rationale ?? null,
      },
    },
    trace: {
      adapter: 'agent',
      proof_input: {
        mode: finding.encoder_mode ?? 'demo',
        source_family: finding.family ?? 'form_workflow_inconsistency',
      },
      transformation_notes: [
        'Agent output normalized into deterministic claim fields.',
        'Rationale preserved for reviewer inspection.',
      ],
    },
    verification: {
      trust_state: finding.trust_state ?? 'demo_only',
      proof_status: finding.proof_status ?? 'generated',
      verifier_status: finding.verifier_status ?? 'passed',
      satisfiable: finding.satisfiable ?? true,
      demo_only: finding.demo_only ?? true,
      artifact_ref: finding.artifact_ref ?? null,
    },
    summary: finding.summary ?? 'Mock agent finding normalized into the canonical trust-layer artifact.',
  });
}

export function adaptOutboundMessageAction(action = {}) {
  const family = action.family ?? 'OUTBOUND_MESSAGE_POLICY';
  return buildAgentActionArtifact({
    finding_id:
      action.finding_id ??
      makeId('message', slug(action.message_id ?? action.recipient ?? family, 'action')),
    source: {
      tool: action.tool ?? 'mock-agent',
      kind: 'agent_action',
      finding_id: action.message_id ?? action.finding_id ?? null,
      event_id: action.event_id ?? null,
    },
    target: {
      asset: action.asset ?? 'customer-communication',
      workflow_id: action.workflow_id ?? 'outbound_message_review',
    },
    action: {
      type: action.action_type ?? 'outbound_message',
      status: action.status ?? 'draft',
      recipient: action.recipient ?? null,
      channel: action.channel ?? 'email',
    },
    claim: {
      family,
      title: action.title ?? 'Outbound message requires policy review',
      statement:
        action.statement ??
        'Agent-generated outbound message was normalized into a policy-check artifact.',
      severity: action.severity ?? 'medium',
      confidence: action.confidence ?? 0.76,
    },
    evidence: {
      snippet: action.message_body ?? null,
      offset: null,
      locator: action.locator ?? null,
      metadata: {
        subject: action.subject ?? null,
        message_family: action.message_family ?? 'general_outreach',
        required_disclosure: action.required_disclosure ?? null,
        policy_snapshot: action.policy_snapshot ?? null,
        policy_reasons: action.trace_notes ?? [],
      },
    },
    trace: {
      adapter: 'outbound_message',
      proof_input: {
        mode: action.encoder_mode ?? 'demo_policy',
        source_family: family,
      },
      transformation_notes: [
        'Outbound message normalized into canonical action fields.',
        'Policy metadata preserved for review and handoff.',
        ...(action.trace_notes ?? []),
      ],
    },
    verification: {
      trust_state: action.trust_state ?? 'needs_review',
      proof_status: action.proof_status ?? 'policy_checked',
      verifier_status: action.verifier_status ?? 'not_run',
      satisfiable: action.satisfiable ?? null,
      demo_only: action.demo_only ?? true,
      artifact_ref: action.artifact_ref ?? null,
    },
    summary:
      action.summary ??
      'Agent-generated outbound message normalized into a policy-aware action artifact.',
  });
}
