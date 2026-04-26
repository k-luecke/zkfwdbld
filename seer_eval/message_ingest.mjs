// seer_eval/message_ingest.mjs - file-based ingest path for outbound message drafts.

import { readFileSync } from 'fs';

import { policyReviewedOutboundMessages } from './message_pipeline.mjs';

function normalizeDraft(draft = {}, index = 0) {
  return {
    tool: draft.source_system ?? draft.tool ?? 'external-agent',
    message_id: draft.message_id ?? draft.action_id ?? `INGEST-${index + 1}`,
    recipient: draft.recipient ?? null,
    channel: draft.channel ?? 'email',
    subject: draft.subject ?? null,
    message_family: draft.message_family ?? 'general_outreach',
    message_body: draft.message_body ?? '',
    workflow_id: draft.workflow_id ?? 'inbound_message_review',
    status: draft.status ?? 'draft',
    asset: draft.asset ?? 'customer-communication',
    locator: draft.locator ?? null,
    event_id: draft.event_id ?? null,
    metadata: draft.metadata ?? {},
  };
}

export function parseMessageDraftFile(filePath) {
  const raw = readFileSync(filePath, 'utf-8');
  const parsed = JSON.parse(raw);
  const drafts = Array.isArray(parsed) ? parsed : parsed.messages ?? parsed.actions ?? [];

  if (!Array.isArray(drafts)) {
    throw new Error('Message draft file must contain an array or a { "messages": [...] } / { "actions": [...] } object.');
  }

  return drafts.map((draft, index) => normalizeDraft(draft, index));
}

export function reviewedArtifactsFromDraftFile(filePath, policy) {
  return policyReviewedOutboundMessages(parseMessageDraftFile(filePath), policy);
}
