import { defaultHarnessArtifacts, verifiedHarnessArtifacts } from '../seer_eval/harness_pipeline.mjs';

const mode = process.argv[2] ?? 'default';
const artifacts =
  mode === 'verified' ? verifiedHarnessArtifacts() : defaultHarnessArtifacts();

console.log(JSON.stringify(artifacts, null, 2));
