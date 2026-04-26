// seer_eval/finding_artifact.mjs — canonical verified-finding artifact builder.

function normalizeSource(source = {}) {
  return {
    tool: source.tool ?? null,
    kind: source.kind ?? null,
    finding_id: source.finding_id ?? null,
    event_id: source.event_id ?? null,
  };
}

function normalizeTarget(target = {}) {
  return {
    url: target.url ?? null,
    asset: target.asset ?? null,
    workflow_id: target.workflow_id ?? null,
  };
}

function normalizeAction(action = {}) {
  return {
    type: action.type ?? null,
    status: action.status ?? null,
    recipient: action.recipient ?? null,
    channel: action.channel ?? null,
  };
}

function normalizeClaim(claim = {}) {
  return {
    family: claim.family ?? null,
    title: claim.title ?? null,
    statement: claim.statement ?? null,
    severity: claim.severity ?? null,
    confidence: claim.confidence ?? null,
  };
}

function normalizeEvidence(evidence = {}) {
  return {
    snippet: evidence.snippet ?? null,
    offset: evidence.offset ?? null,
    locator: evidence.locator ?? null,
    metadata: evidence.metadata ?? {},
  };
}

function normalizeTrace(trace = {}) {
  return {
    adapter: trace.adapter ?? null,
    proof_input: trace.proof_input ?? null,
    transformation_notes: trace.transformation_notes ?? [],
  };
}

function normalizeVerification(verification = {}) {
  return {
    trust_state: verification.trust_state ?? 'error',
    proof_status: verification.proof_status ?? null,
    verifier_status: verification.verifier_status ?? null,
    satisfiable: verification.satisfiable ?? null,
    demo_only: verification.demo_only ?? null,
    artifact_ref: verification.artifact_ref ?? null,
  };
}

function buildArtifact(input = {}, artifactType) {
  return {
    artifact_version: '0.1.0',
    artifact_type: artifactType,
    finding_id: input.finding_id ?? null,
    ts: input.ts ?? new Date().toISOString(),
    source: normalizeSource(input.source),
    target: normalizeTarget(input.target),
    action: normalizeAction(input.action),
    claim: normalizeClaim(input.claim),
    evidence: normalizeEvidence(input.evidence),
    trace: normalizeTrace(input.trace),
    verification: normalizeVerification(input.verification),
    summary: input.summary ?? null,
  };
}

export function buildFindingArtifact(input = {}) {
  return buildArtifact(input, 'verified_finding');
}

export function buildAgentActionArtifact(input = {}) {
  return buildArtifact(input, 'agent_action');
}
