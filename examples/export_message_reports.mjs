import path from 'path';

import { reviewedOutboundMessageArtifacts } from '../seer_eval/message_pipeline.mjs';
import { exportFindingReportSet } from '../seer_eval/report_exporter.mjs';

const outputDir =
  process.argv[2] ?? path.join(process.cwd(), 'artifacts', 'message-action-reviewed');
const artifacts = reviewedOutboundMessageArtifacts();

const result = exportFindingReportSet(artifacts, outputDir, {
  title: 'Outbound Message Action Review',
});

console.log(JSON.stringify(result, null, 2));
