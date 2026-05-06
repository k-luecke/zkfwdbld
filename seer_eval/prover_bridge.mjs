// seer_eval/prover_bridge.mjs - local bridge to the Rust proof core.

import { spawnSync } from 'child_process';

function toWslPath(value) {
  if (!value) {
    return null;
  }

  if (value.startsWith('/')) {
    return value;
  }

  const uncMatch = /^\\\\wsl\.localhost\\[^\\]+\\(.+)$/.exec(value);
  if (uncMatch) {
    return `/${uncMatch[1].replace(/\\/g, '/')}`;
  }

  return null;
}

function runCommand(command, args, request) {
  return spawnSync(command, args, {
    input: JSON.stringify(request),
    encoding: 'utf-8',
  });
}

function runRustRequest(request) {
  let child = runCommand(
    'cargo',
    ['run', '--quiet', '--example', 'prove_request'],
    request
  );

  if (child.error && child.error.code === 'ENOENT') {
    const wslCwd = toWslPath(process.cwd());
    if (!wslCwd) {
      throw child.error;
    }

    // Audit H-2 (#6): use `wsl.exe --cd <path>` instead of
    // `bash -lc "cd '${wslCwd}' && ..."`. With --cd the path is a
    // single argv to wsl.exe; there is no shell, so a directory
    // containing `'`, `;`, `$`, or any other metacharacter cannot
    // break out of the quoted context.
    child = runCommand(
      'wsl.exe',
      ['--cd', wslCwd, 'cargo', 'run', '--quiet', '--example', 'prove_request'],
      request
    );
  }

  if (child.status !== 0) {
    throw new Error((child.stderr || child.stdout || 'Rust proof bridge failed').trim());
  }

  return JSON.parse(child.stdout);
}

export function proveAndVerify(request) {
  const prove = runRustRequest(request.proof_request);

  if (!prove.success || prove.satisfiable !== true || !prove.witness) {
    return {
      prove,
      verify: null,
      trust_state: 'error',
      verifier_status: 'not_run',
    };
  }

  const verify = runRustRequest({
    ...request.verify_request_base,
    witness: prove.witness,
  });

  return {
    prove,
    verify,
    trust_state: verify.success && verify.satisfiable === true ? 'verified' : 'error',
    verifier_status: verify.success && verify.satisfiable === true ? 'passed' : 'failed',
  };
}
