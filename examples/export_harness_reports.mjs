import path from 'path';

import { defaultHarnessArtifacts, verifiedHarnessArtifacts } from '../seer_eval/harness_pipeline.mjs';
import { exportFindingReportSet } from '../seer_eval/report_exporter.mjs';

const mode = process.argv[2] ?? 'default';
const outputDir =
  process.argv[3] ?? path.join(process.cwd(), 'artifacts', `harness-report-${mode}`);
const artifacts =
  mode === 'verified' ? verifiedHarnessArtifacts() : defaultHarnessArtifacts();

const result = exportFindingReportSet(artifacts, outputDir, {
  title:
    mode === 'verified'
      ? 'Harness Verified Findings Report'
      : 'Harness Demo Findings Report',
});

console.log(JSON.stringify(result, null, 2));
