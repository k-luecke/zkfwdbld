import path from 'path';

import {
  artifactsFromScannerFindings,
  defaultScannerFindings,
  verifiedScannerArtifacts,
} from '../seer_eval/scanner_pipeline.mjs';
import { exportFindingReportSet } from '../seer_eval/report_exporter.mjs';

const mode = process.argv[2] ?? 'default';
const outputDir =
  process.argv[3] ?? path.join(process.cwd(), 'artifacts', `scanner-report-${mode}`);
const findings = defaultScannerFindings();
const artifacts =
  mode === 'verified' ? verifiedScannerArtifacts(findings) : artifactsFromScannerFindings(findings);

const result = exportFindingReportSet(artifacts, outputDir, {
  title:
    mode === 'verified'
      ? 'Scanner Verified Findings Report'
      : 'Scanner Demo Findings Report',
});

console.log(JSON.stringify(result, null, 2));
