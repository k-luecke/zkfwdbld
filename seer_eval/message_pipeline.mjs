// seer_eval/message_pipeline.mjs - outbound message action pipeline.

import { adaptOutboundMessageAction } from './adapters.mjs';
import { defaultOutboundMessages, evaluateOutboundMessagePolicy } from './message_policy.mjs';

export function artifactsFromOutboundMessages(messages = []) {
  return messages.map(message => adaptOutboundMessageAction(message));
}

export function policyReviewedOutboundMessages(messages = []) {
  return messages.map(message => {
    const result = evaluateOutboundMessagePolicy(message);
    return adaptOutboundMessageAction({
      ...message,
      title:
        result.trust_state === 'ready_to_send'
          ? 'Outbound message is ready to send'
          : 'Outbound message requires review',
      statement:
        result.trust_state === 'ready_to_send'
          ? 'Outbound message satisfied the current bounded send policy.'
          : 'Outbound message failed or exceeded the current bounded send policy.',
      trust_state: result.trust_state,
      proof_status: 'policy_checked',
      verifier_status: result.verifier_status,
      demo_only: result.demo_only,
      summary:
        result.trust_state === 'ready_to_send'
          ? 'Outbound message passed the bounded send-policy check.'
          : 'Outbound message did not satisfy the bounded send-policy check.',
      required_disclosure: result.policy_snapshot.required_disclosure,
      confidence: result.trust_state === 'ready_to_send' ? 0.91 : 0.42,
      trace_notes: result.reasons,
      policy_snapshot: result.policy_snapshot,
    });
  }).map(artifact => ({
    ...artifact,
    trace: {
      ...artifact.trace,
      proof_input: {
        ...artifact.trace.proof_input,
        policy_mode: 'bounded_send_policy',
      },
      transformation_notes: [
        ...artifact.trace.transformation_notes,
        'Outbound message checked against bounded send-policy constraints.',
      ],
    },
  }));
}

export function defaultOutboundMessageArtifacts() {
  return artifactsFromOutboundMessages(defaultOutboundMessages());
}

export function reviewedOutboundMessageArtifacts() {
  return policyReviewedOutboundMessages(defaultOutboundMessages());
}
