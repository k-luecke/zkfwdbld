import { artifactsFromScannerFindings, defaultScannerFindings, verifiedScannerArtifacts } from '../seer_eval/scanner_pipeline.mjs';

const mode = process.argv[2] ?? 'default';
const findings = defaultScannerFindings();
const artifacts =
  mode === 'verified' ? verifiedScannerArtifacts(findings) : artifactsFromScannerFindings(findings);

console.log(JSON.stringify(artifacts, null, 2));
