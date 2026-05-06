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

// M-6 (#17): canonical zero-width / format-character set we strip BEFORE
// phrase matching so attackers can't hide e.g. "guara<ZWSP>ntee".
// U+200B ZWSP, U+200C ZWNJ, U+200D ZWJ, U+FEFF BOM, U+2060 WJ,
// U+180E MVS, U+00AD SHY, U+034F CGJ, U+FE00–U+FE0F variation selectors.
const ZERO_WIDTH_RE = /[​‌‍﻿⁠᠎­͏︀-️]/g;

// Stricter normaliser for disallowed-phrase matching: NFKC fold + zero-width
// strip on top of normaliseForMatch. NFKC normalises full-width forms
// ("ｇｕａｒａｎｔｅｅ") and compatibility characters ("ﬁ" -> "fi"). Tradeoff:
// NFKC also folds e.g. "²" -> "2" and "㎏" -> "kg" — acceptable surface for a
// deny-list of business phrases that don't contain those code points.
function normaliseForPhraseMatch(text) {
  return normaliseForMatch(text).normalize('NFKC').replace(ZERO_WIDTH_RE, '');
}

// Build a Unicode-property word-boundary regex for a phrase. JS's \b only
// understands ASCII word chars, so we use lookarounds against \p{L}\p{N}.
// Internal whitespace in the phrase is relaxed to \s+ so an attacker can't
// bypass with NBSP / multiple spaces / newlines between phrase tokens.
function buildPhraseRegex(rawPhrase) {
  const normalised = normaliseForPhraseMatch(rawPhrase);
  const escaped = normalised
    .replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    .replace(/\s+/g, '\\s+');
  return new RegExp(`(?<![\\p{L}\\p{N}])${escaped}(?![\\p{L}\\p{N}])`, 'u');
}

// Memoise compiled phrase regexes — phrases are static per policy load.
const PHRASE_REGEX_CACHE = new WeakMap();
function compilePhraseRegexes(phrases) {
  let cached = PHRASE_REGEX_CACHE.get(phrases);
  if (!cached) {
    cached = phrases.map(buildPhraseRegex);
    PHRASE_REGEX_CACHE.set(phrases, cached);
  }
  return cached;
}

function includesAnyPhrase(text, phrases) {
  const normalised = normaliseForPhraseMatch(text);
  const regexes = compilePhraseRegexes(phrases);
  return regexes.some(re => re.test(normalised));
}

export function evaluateOutboundMessagePolicy(message = {}, policy = DEFAULT_POLICY) {
  const recipientDomain = domainFromRecipient(message.recipient);
  const messageFamily = message.message_family ?? 'general_outreach';
  const body = message.message_body ?? '';
  const channel = message.channel ?? 'email';
  const subject = message.subject ?? '';
  const reasons = [];

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

  if (!policy.approved_families.includes(messageFamily)) {
    // Family short-circuit preserves the unsupported_family contract for the
    // two prose branches in report_renderer.mjs, but surfaces any other
    // policy violations via additional_reasons so the operator does not lose
    // triage data when both an unapproved family AND other failures are
    // present (M-5 / GH #16).
    return {
      trust_state: 'unsupported_policy',
      verifier_status: 'unsupported_family',
      demo_only: true,
      reasons: [`Message family ${messageFamily} is not in the approved family set.`],
      additional_reasons: reasons,
      policy_snapshot: policy,
    };
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
