import {
  artifactsFromScannerFindings,
  defaultScannerFindings,
  verifiedScannerArtifacts,
} from '../seer_eval/scanner_pipeline.mjs';
import { renderFindingReportSet } from '../seer_eval/report_renderer.mjs';

const mode = process.argv[2] ?? 'default';
const findings = defaultScannerFindings();
const artifacts =
  mode === 'verified' ? verifiedScannerArtifacts(findings) : artifactsFromScannerFindings(findings);

console.log(
  renderFindingReportSet(artifacts, {
    title:
      mode === 'verified'
        ? 'Scanner Verified Findings Report'
        : 'Scanner Demo Findings Report',
  })
);
