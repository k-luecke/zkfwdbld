import { defaultOpsPaths, runOutboundMessageOpsLoop } from '../seer_eval/ops_runner.mjs';

const paths = defaultOpsPaths(process.cwd());
const queuePath = process.argv[2] ?? paths.queue_path;
const outputDir = process.argv[3] ?? paths.output_dir;

const result = runOutboundMessageOpsLoop(queuePath, outputDir);

console.log(JSON.stringify(result, null, 2));
