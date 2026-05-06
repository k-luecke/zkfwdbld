// seer_eval/message_policy.mjs - mocked outbound-message policy evaluator.

import { readFileSync } from 'fs';

const DEFAULT_POLICY = {
  allowlisted_domains: ['customer.example', 'prospect.example'],
  allowlisted_channels: ['email'],
  blocked_recipients: [],
  disallowed_phrases: ['guarantee', 'guaranteed results', 'no-risk promise'],
  required_disclosure: 'Sent by AI assistant',
  required_subject_prefix: '',
  max_body_chars: 500,
  approved_families: ['support_followup', 'demo_outreach'],
};

function readJson(filePath) {
  return JSON.parse(readFileSync(filePath, 'utf-8'));
}

export function loadOutboundMessagePolicy(filePath) {
  const parsed = readJson(filePath);
  return {
    allowlisted_domains: parsed.allowlisted_domains ?? DEFAULT_POLICY.allowlisted_domains,
    allowlisted_channels: parsed.allowlisted_channels ?? DEFAULT_POLICY.allowlisted_channels,
    blocked_recipients: parsed.blocked_recipients ?? DEFAULT_POLICY.blocked_recipients,
    disallowed_phrases: parsed.disallowed_phrases ?? DEFAULT_POLICY.disallowed_phrases,
    required_disclosure: parsed.required_disclosure ?? DEFAULT_POLICY.required_disclosure,
    required_subject_prefix: parsed.required_subject_prefix ?? DEFAULT_POLICY.required_subject_prefix,
    max_body_chars: parsed.max_body_chars ?? DEFAULT_POLICY.max_body_chars,
    approved_families: parsed.approved_families ?? DEFAULT_POLICY.approved_families,
  };
}

function domainFromRecipient(recipient) {
  if (!recipient || !recipient.includes('@')) {
    return null;
  }
  return recipient.split('@')[1].toLowerCase();
}

// Shared text normaliser for policy substring matching.
// Intentionally minimal: lowercase + trim only. We do NOT collapse internal
// whitespace (would let an attacker hide adversarial padding inside an
// otherwise-matching disclosure) and we do NOT strip HTML (bodies are
// plaintext in every current ingest path — see defaultOutboundMessages,
// examples/fixtures/real_message_drafts.json, ops/queue/outbound_messages.json).
// Re-used by M-6 (#17) — keep this seam stable.
function normaliseForMatch(text) {
  return String(text ?? '').toLowerCase().trim();
}

function includesAnyPhrase(text, phrases) {
  const normalised = normaliseForMatch(text);
  return phrases.some(phrase => normalised.includes(normaliseForMatch(phrase)));
}

export function evaluateOutboundMessagePolicy(message = {}, policy = DEFAULT_POLICY) {
  const recipientDomain = domainFromRecipient(message.recipient);
  const messageFamily = message.message_family ?? 'general_outreach';
  const body = message.message_body ?? '';
  const channel = message.channel ?? 'email';
  const subject = message.subject ?? '';
  const reasons = [];

  if (!policy.approved_families.includes(messageFamily)) {
    return {
      trust_state: 'unsupported_policy',
      verifier_status: 'unsupported_family',
      demo_only: true,
      reasons: [`Message family ${messageFamily} is not in the approved family set.`],
      policy_snapshot: policy,
    };
  }

  if (!recipientDomain || !policy.allowlisted_domains.includes(recipientDomain)) {
    reasons.push('Recipient domain is not allowlisted.');
  }
  if (!policy.allowlisted_channels.includes(channel)) {
    reasons.push('Message channel is not allowlisted.');
  }
  if ((policy.blocked_recipients ?? []).includes(message.recipient)) {
    reasons.push('Recipient is explicitly blocked.');
  }
  if (!normaliseForMatch(body).includes(normaliseForMatch(policy.required_disclosure))) {
    reasons.push('Required disclosure string is missing.');
  }
  if (policy.required_subject_prefix && !subject.startsWith(policy.required_subject_prefix)) {
    reasons.push('Required subject prefix is missing.');
  }
  if (body.length > policy.max_body_chars) {
    reasons.push('Message body exceeds the maximum allowed length.');
  }
  if (includesAnyPhrase(body, policy.disallowed_phrases)) {
    reasons.push('Message contains a disallowed promise phrase.');
  }

  return {
    trust_state: reasons.length === 0 ? 'ready_to_send' : 'needs_review',
    verifier_status: reasons.length === 0 ? 'policy_passed' : 'policy_failed',
    demo_only: true,
    reasons,
    policy_snapshot: policy,
  };
}

export function defaultOutboundMessages() {
  return [
    {
      tool: 'mock-agent',
      message_id: 'MSG-1001',
      recipient: 'owner@customer.example',
      channel: 'email',
      subject: 'Follow-up on your onboarding request',
      message_family: 'support_followup',
      message_body:
        'Hello,\n\nSent by AI assistant.\nWe reviewed your onboarding request and can schedule a follow-up for Tuesday.\n\nBest,\nzkfwdbld',
    },
    {
      tool: 'mock-agent',
      message_id: 'MSG-1002',
      recipient: 'buyer@unknown-domain.test',
      channel: 'email',
      subject: 'Guaranteed results from our new workflow',
      message_family: 'demo_outreach',
      message_body:
        'Hello,\n\nWe guarantee faster results with no-risk promise.\nReply if you want a live demo.\n\nBest,\nzkfwdbld agent',
    },
  ];
}

export { DEFAULT_POLICY };
