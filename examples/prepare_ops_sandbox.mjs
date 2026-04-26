import { cpSync, mkdirSync } from 'fs';
import path from 'path';

const rootDir = process.cwd();
const sandboxDir =
  process.argv[2] ?? path.join(rootDir, 'artifacts', 'ops-sandbox');
const queueTarget = path.join(sandboxDir, 'outbound_messages.json');
const policyTarget = path.join(sandboxDir, 'outbound_message_policy.json');

mkdirSync(sandboxDir, { recursive: true });
cpSync(path.join(rootDir, 'ops', 'queue', 'outbound_messages.json'), queueTarget);
cpSync(path.join(rootDir, 'ops', 'policies', 'outbound_message_policy.json'), policyTarget);

console.log(
  JSON.stringify(
    {
      sandbox_dir: sandboxDir,
      queue_path: queueTarget,
      policy_path: policyTarget,
      run_example: `node examples/run_ops_loop.mjs "${queueTarget}" "${policyTarget}"`,
    },
    null,
    2
  )
);
