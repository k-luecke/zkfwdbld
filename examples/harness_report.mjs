import { defaultHarnessArtifacts, verifiedHarnessArtifacts } from '../seer_eval/harness_pipeline.mjs';
import { renderFindingReportSet } from '../seer_eval/report_renderer.mjs';

const mode = process.argv[2] ?? 'default';
const artifacts =
  mode === 'verified' ? verifiedHarnessArtifacts() : defaultHarnessArtifacts();

console.log(
  renderFindingReportSet(artifacts, {
    title:
      mode === 'verified'
        ? 'Harness Verified Findings Report'
        : 'Harness Demo Findings Report',
  })
);
