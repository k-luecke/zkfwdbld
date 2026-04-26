import path from 'path';

import { reviewedArtifactsFromDraftFile } from '../seer_eval/message_ingest.mjs';
import { exportFindingReportSet } from '../seer_eval/report_exporter.mjs';

const inputPath =
  process.argv[2] ??
  path.join(process.cwd(), 'examples', 'fixtures', 'real_message_drafts.json');
const outputDir =
  process.argv[3] ?? path.join(process.cwd(), 'artifacts', 'message-ingest-reviewed');

const artifacts = reviewedArtifactsFromDraftFile(inputPath);
const result = exportFindingReportSet(artifacts, outputDir, {
  title: 'Inbound Message Draft Review',
});

console.log(JSON.stringify({ input_path: inputPath, ...result }, null, 2));
