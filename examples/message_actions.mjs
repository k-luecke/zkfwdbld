import {
  defaultOutboundMessageArtifacts,
  reviewedOutboundMessageArtifacts,
} from '../seer_eval/message_pipeline.mjs';
import { renderFindingReportSet } from '../seer_eval/report_renderer.mjs';

const mode = process.argv[2] ?? 'default';
const artifacts =
  mode === 'reviewed' ? reviewedOutboundMessageArtifacts() : defaultOutboundMessageArtifacts();

console.log(
  renderFindingReportSet(artifacts, {
    title:
      mode === 'reviewed'
        ? 'Outbound Message Action Review'
        : 'Outbound Message Action Demo',
  })
);
