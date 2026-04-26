import { defaultOpsPaths, runOutboundMessageOpsLoop } from '../seer_eval/ops_runner.mjs';

const paths = defaultOpsPaths(process.cwd());
const queuePath = process.argv[2] ?? paths.queue_path;
const policyPath = process.argv[3] ?? paths.policy_path;
const outputDir = process.argv[4] ?? paths.output_dir;

const result = runOutboundMessageOpsLoop(queuePath, outputDir, {
  policy_path: policyPath,
});

console.log(JSON.stringify(result, null, 2));
