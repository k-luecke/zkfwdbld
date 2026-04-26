// seer_eval/report_renderer.mjs - human-readable report renderer for verified findings.

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function line(label, value) {
  return `${label}: ${value ?? 'n/a'}`;
}

function paragraphList(items) {
  return items.length > 0 ? items.map(item => `- ${item}`) : ['- none'];
}

function yesNo(value) {
  if (value === true) {
    return 'yes';
  }
  if (value === false) {
    return 'no';
  }
  return 'n/a';
}

function formatEvidence(artifact) {
  const snippet = artifact.evidence?.snippet ?? 'n/a';
  const locator = artifact.evidence?.locator ?? 'n/a';
  const offset = artifact.evidence?.offset ?? 'n/a';
  return [
    line('locator', locator),
    line('offset', offset),
    'snippet:',
    snippet,
  ].join('\n');
}

function formatAction(artifact) {
  return [
    line('type', artifact.action?.type ?? 'n/a'),
    line('status', artifact.action?.status ?? 'n/a'),
    line('recipient', artifact.action?.recipient ?? 'n/a'),
    line('channel', artifact.action?.channel ?? 'n/a'),
  ].join('\n');
}

function formatTrace(artifact) {
  const proofInput = artifact.trace?.proof_input ?? {};
  const notes = asList(artifact.trace?.transformation_notes);
  const noteLines = notes.length > 0 ? notes.map(note => `- ${note}`) : ['- none'];

  return [
    line('adapter', artifact.trace?.adapter ?? 'n/a'),
    line('mode', proofInput.mode ?? 'n/a'),
    line('source_family', proofInput.source_family ?? 'n/a'),
    line('category', proofInput.category ?? 'n/a'),
    'notes:',
    ...noteLines,
  ].join('\n');
}

function formatVerification(artifact) {
  const verification = artifact.verification ?? {};
  return [
    line('trust_state', verification.trust_state ?? 'n/a'),
    line('proof_status', verification.proof_status ?? 'n/a'),
    line('verifier_status', verification.verifier_status ?? 'n/a'),
    line('satisfiable', verification.satisfiable ?? 'n/a'),
    line('demo_only', yesNo(verification.demo_only)),
  ].join('\n');
}

function deriveRecommendedAction(artifact) {
  const trustState = artifact.verification?.trust_state ?? 'unknown';
  const family = artifact.claim?.family ?? 'unknown';
  const artifactType = artifact.artifact_type ?? 'verified_finding';

  if (artifactType === 'agent_action') {
    if (trustState === 'ready_to_send') {
      return `Message action for ${family} can proceed under the current bounded send policy.`;
    }
    if (trustState === 'needs_review') {
      return `Hold ${family} until a human reviewer clears the message for sending.`;
    }
    if (trustState === 'unsupported_policy') {
      return `Do not send ${family} until the action family is mapped to a supported send policy.`;
    }
    if (trustState === 'policy_failed') {
      return `Revise ${family} to satisfy the send policy before attempting delivery.`;
    }
  }

  if (trustState === 'verified') {
    return `Open an engineering ticket for ${family} with this artifact bundle attached.`;
  }
  if (trustState === 'demo_only') {
    return `Treat ${family} as a triage hint and require manual validation before escalation.`;
  }
  if (trustState === 'unsupported') {
    return `Keep ${family} in analyst review until a supported claim encoder exists.`;
  }
  return `Hold ${family} for analyst review because the verification path did not complete cleanly.`;
}

function deriveTrustRationale(artifact) {
  const trustState = artifact.verification?.trust_state ?? 'unknown';
  const sourceKind = artifact.source?.kind ?? 'unknown_source';
  const proofStatus = artifact.verification?.proof_status ?? 'unknown';
  const verifierStatus = artifact.verification?.verifier_status ?? 'unknown';
  const artifactType = artifact.artifact_type ?? 'verified_finding';

  if (artifactType === 'agent_action') {
    if (trustState === 'ready_to_send') {
      return `Derived from ${sourceKind} and cleared by the bounded send-policy check with verifier status ${verifierStatus}.`;
    }
    if (trustState === 'needs_review' || trustState === 'policy_failed') {
      return `Derived from ${sourceKind}, but the bounded send-policy check surfaced issues with verifier status ${verifierStatus}.`;
    }
    if (trustState === 'unsupported_policy') {
      return `Derived from ${sourceKind}, but no supported send-policy mapping exists for this action family yet.`;
    }
  }

  if (trustState === 'verified') {
    return `Derived from ${sourceKind}, encoded into a supported claim, and passed local prove/verify with verifier status ${verifierStatus}.`;
  }
  if (trustState === 'demo_only') {
    return `Derived from ${sourceKind}, but the current path is still demo-only with proof status ${proofStatus}.`;
  }
  if (trustState === 'unsupported') {
    return `Derived from ${sourceKind}, but this claim family does not yet have a supported proof path.`;
  }
  return `Derived from ${sourceKind}, but verification ended in state ${trustState}.`;
}

function deriveOpenQuestions(artifact) {
  const trustState = artifact.verification?.trust_state ?? 'unknown';
  const questions = [];
  const artifactType = artifact.artifact_type ?? 'verified_finding';

  if (artifactType === 'agent_action' && trustState === 'ready_to_send') {
    return questions;
  }

  if (trustState !== 'verified') {
    questions.push(
      artifactType === 'agent_action'
        ? 'Manual confirmation is still required before allowing this action to proceed.'
        : 'Manual confirmation is still required before routing this as a trusted finding.'
    );
  }
  if (artifact.verification?.demo_only === true) {
    questions.push('The artifact reflects a demo-only path rather than a production-bound claim encoder.');
  }
  if (!artifact.target?.url && !artifact.target?.workflow_id) {
    questions.push('Target context is incomplete and should be enriched before handoff.');
  }

  return questions;
}

function formatHandoff(artifact) {
  return [
    line('recommended_action', deriveRecommendedAction(artifact)),
    line('trust_rationale', deriveTrustRationale(artifact)),
    'open_questions:',
    ...paragraphList(deriveOpenQuestions(artifact)),
  ].join('\n');
}

function countByTrustState(artifacts = []) {
  return artifacts.reduce((acc, artifact) => {
    const state = artifact.verification?.trust_state ?? 'unknown';
    acc[state] = (acc[state] ?? 0) + 1;
    return acc;
  }, {});
}

function summarizeHandoffReadiness(artifacts = []) {
  const readyCount = artifacts.filter(
    artifact =>
      artifact.verification?.trust_state === 'verified' ||
      artifact.verification?.trust_state === 'ready_to_send'
  ).length;
  const demoOnlyCount = artifacts.filter(
    artifact => artifact.verification?.demo_only === true
  ).length;
  const actionArtifacts = artifacts.filter(artifact => artifact.artifact_type === 'agent_action');

  if (actionArtifacts.length === artifacts.length && readyCount === artifacts.length && readyCount > 0) {
    return 'All actions in this report are ready to proceed under the current bounded policy.';
  }
  if (verifiedCountOrReady(artifacts) === artifacts.length && readyCount > 0) {
    return 'All findings in this report are ready for high-confidence engineering handoff.';
  }
  if (actionArtifacts.length === artifacts.length && readyCount > 0) {
    return `${readyCount} action(s) are ready to proceed, while ${artifacts.length - readyCount} still require review or policy support.`;
  }
  if (readyCount > 0) {
    return `${readyCount} finding(s) are ready for high-confidence handoff, while ${demoOnlyCount} still require manual validation or product support.`;
  }
  if (actionArtifacts.length === artifacts.length) {
    return 'No actions in this report are ready to proceed yet.';
  }
  return 'No findings in this report are ready for high-confidence handoff yet.';
}

function verifiedCountOrReady(artifacts = []) {
  return artifacts.filter(
    artifact =>
      artifact.verification?.trust_state === 'verified' ||
      artifact.verification?.trust_state === 'ready_to_send'
  ).length;
}

export function renderFindingReport(artifact = {}) {
  const heading = artifact.artifact_type === 'agent_action' ? 'Agent Action' : 'Verified Finding';
  return [
    `# ${heading}: ${artifact.finding_id ?? 'unknown'}`,
    '',
    '## Summary',
    artifact.summary ?? 'n/a',
    '',
    '## Source',
    line('tool', artifact.source?.tool ?? 'n/a'),
    line('kind', artifact.source?.kind ?? 'n/a'),
    line('source_finding_id', artifact.source?.finding_id ?? 'n/a'),
    '',
    '## Target',
    line('url', artifact.target?.url ?? 'n/a'),
    line('asset', artifact.target?.asset ?? 'n/a'),
    line('workflow_id', artifact.target?.workflow_id ?? 'n/a'),
    '',
    '## Action',
    formatAction(artifact),
    '',
    '## Claim',
    line('family', artifact.claim?.family ?? 'n/a'),
    line('title', artifact.claim?.title ?? 'n/a'),
    line('severity', artifact.claim?.severity ?? 'n/a'),
    line('confidence', artifact.claim?.confidence ?? 'n/a'),
    line('statement', artifact.claim?.statement ?? 'n/a'),
    '',
    '## Evidence',
    formatEvidence(artifact),
    '',
    '## Verification',
    formatVerification(artifact),
    '',
    '## Handoff',
    formatHandoff(artifact),
    '',
    '## Trace',
    formatTrace(artifact),
  ].join('\n');
}

export function renderFindingReportSet(artifacts = [], options = {}) {
  const title = options.title ?? 'zkfwdbld Verified Findings Report';
  const counts = countByTrustState(artifacts);
  const countSummary = Object.entries(counts)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([state, count]) => `${state}=${count}`)
    .join(', ');

  const sections = artifacts.map(renderFindingReport);

  return [
    `# ${title}`,
    '',
    line('artifact_count', artifacts.length),
    line('trust_states', countSummary || 'none'),
    line('handoff_readiness', summarizeHandoffReadiness(artifacts)),
    '',
    ...sections.flatMap((section, index) =>
      index === 0 ? [section] : ['', '---', '', section]
    ),
  ].join('\n');
}

export function buildReportSummary(artifacts = [], options = {}) {
  const counts = countByTrustState(artifacts);
  return {
    title: options.title ?? 'zkfwdbld Verified Findings Report',
    artifact_count: artifacts.length,
    trust_states: counts,
    handoff_readiness: summarizeHandoffReadiness(artifacts),
    verified_finding_ids: artifacts
      .filter(artifact => artifact.verification?.trust_state === 'verified')
      .map(artifact => artifact.finding_id),
  };
}

export function renderEngineeringHandoff(artifacts = [], options = {}) {
  const summary = buildReportSummary(artifacts, options);
  const verifiedArtifacts = artifacts.filter(
    artifact =>
      artifact.verification?.trust_state === 'verified' ||
      artifact.verification?.trust_state === 'ready_to_send'
  );
  const pendingArtifacts = artifacts.filter(
    artifact =>
      artifact.verification?.trust_state !== 'verified' &&
      artifact.verification?.trust_state !== 'ready_to_send'
  );

  return [
    `# ${summary.title} Engineering Handoff`,
    '',
    `Readiness: ${summary.handoff_readiness}`,
    '',
    '## Ready Now',
    ...paragraphList(
      verifiedArtifacts.map(artifact =>
        `${artifact.finding_id}: ${artifact.claim?.title ?? artifact.claim?.family ?? 'unknown'} at ${artifact.target?.url ?? artifact.target?.workflow_id ?? 'unknown target'}`
      )
    ),
    '',
    '## Needs Manual Review',
    ...paragraphList(
      pendingArtifacts.map(artifact =>
        `${artifact.finding_id}: ${artifact.claim?.family ?? 'unknown'} remains ${artifact.verification?.trust_state ?? 'unknown'}`
      )
    ),
    '',
    '## Operator Notes',
    '- Attach the per-finding bundle when opening an engineering ticket.',
    '- Verified findings or ready-to-send actions can move directly into the next workflow step with this artifact.',
    '- Demo-only, unsupported, or policy-failed entries should stay in review until a supported path exists.',
  ].join('\n');
}
