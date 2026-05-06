// seer_eval/prover_bridge.mjs - local bridge to the Rust proof core.

import { spawnSync } from 'child_process';

// Audit M-8 (GH #19): bound spawnSync time and output to prevent a
// runaway/oversized cargo subprocess from hanging the bridge or
// exhausting Node's heap. Both knobs are env-configurable so CI and
// cold-build scenarios can override the defaults without code changes.
const DEFAULT_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
const DEFAULT_MAX_BUFFER = 16 * 1024 * 1024; // 16 MiB

function resolveTimeoutMs() {
  const raw = process.env.SEER_PROVER_TIMEOUT_MS;
  if (raw === undefined || raw === '') return DEFAULT_TIMEOUT_MS;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_TIMEOUT_MS;
}

function resolveMaxBuffer() {
  const raw = process.env.SEER_PROVER_MAX_BUFFER;
  if (raw === undefined || raw === '') return DEFAULT_MAX_BUFFER;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : DEFAULT_MAX_BUFFER;
}

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
  // Bounds applied here (not at call sites) so both the direct `cargo`
  // path and the `wsl.exe` fallback in runRustRequest inherit them.
  // killSignal is intentionally left at Node's default (SIGTERM): cargo
  // and the rustc child it spawns rely on graceful termination to clean
  // up incremental-build tmpfiles; SIGKILL would orphan them.
  return spawnSync(command, args, {
    input: JSON.stringify(request),
    encoding: 'utf-8',
    timeout: resolveTimeoutMs(),
    maxBuffer: resolveMaxBuffer(),
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

  // Distinguish the two new failure modes from generic non-zero exits.
  // spawnSync surfaces timeout via child.error.code === 'ETIMEDOUT' and
  // buffer overflow via child.error.code === 'ENOBUFS'.
  if (child.error) {
    if (child.error.code === 'ETIMEDOUT') {
      throw new Error(
        `Rust proof bridge timed out after ${resolveTimeoutMs()} ms ` +
        `(set SEER_PROVER_TIMEOUT_MS to override)`
      );
    }
    if (child.error.code === 'ENOBUFS') {
      throw new Error(
        `Rust proof bridge output exceeded ${resolveMaxBuffer()} bytes ` +
        `(set SEER_PROVER_MAX_BUFFER to override)`
      );
    }
    throw child.error;
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
