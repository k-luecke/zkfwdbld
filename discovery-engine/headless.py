#!/usr/bin/env python3
"""headless.py — the one place that shells out to `claude -p`.

Both the contract surfacer and the science generators need "run a prompt
unattended, get JSON back". Doing that in one place means the failure modes are
handled once, and handled LOUDLY:

    `claude` not installed          -> GenerationUnavailable
    non-zero exit / timeout          -> GenerationUnavailable
    output that is not the JSON we asked for -> GenerationUnavailable

Why raise instead of returning []? Because [] means "the expert looked and found
nothing", and a broken pipe must never be able to impersonate that. An empty
list is a finding about the target; an exception is a finding about the engine.
The run report shows the two in different columns.
"""

from __future__ import annotations

import json
import shutil
import subprocess

DEFAULT_TOOLS = "Read,Grep,Bash"
DEFAULT_TIMEOUT = 1800          # 30 min: an overnight lane, not an API call


class GenerationUnavailable(RuntimeError):
    """The generator could not be run, or produced nothing parseable."""


def claude_available() -> bool:
    return shutil.which("claude") is not None


def run_claude_json(
    prompt: str,
    *,
    model: str = "sonnet",
    tools: str = DEFAULT_TOOLS,
    add_dir: str | None = None,
    cwd: str | None = None,
    max_turns: int = 30,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """Run one headless prompt and return the list of JSON records it emitted."""
    if not claude_available():
        raise GenerationUnavailable("`claude` is not on PATH")

    cmd = ["claude", "-p", prompt,
           "--model", model,
           "--output-format", "json",
           "--max-turns", str(max_turns),
           "--allowedTools", tools]
    if add_dir:
        cmd += ["--add-dir", add_dir]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise GenerationUnavailable(f"timed out after {timeout}s") from exc
    except OSError as exc:
        raise GenerationUnavailable(f"could not exec claude: {exc}") from exc
    if proc.returncode != 0:
        raise GenerationUnavailable(
            f"claude exited {proc.returncode}: {proc.stderr.strip()[:400]}")
    return parse_records(proc.stdout)


def parse_records(stdout: str) -> list[dict]:
    """Pull the record list out of `claude --output-format json` output.

    The envelope's `result` field is the assistant's final TEXT, not a decoded
    object — so it has to be parsed a second time, and it may arrive fenced in a
    ```json block. Both shapes are handled here rather than at four call sites.
    """
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise GenerationUnavailable(
            f"envelope was not JSON: {stdout.strip()[:200]!r}") from exc

    payload = envelope.get("result", envelope) if isinstance(envelope, dict) else envelope
    if isinstance(payload, str):
        payload = _decode_text(payload)
    return _as_records(payload)


def _decode_text(text: str) -> object:
    body = text.strip()
    if body.startswith("```"):
        lines = body.splitlines()
        body = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise GenerationUnavailable(
            f"result text was not JSON: {body[:200]!r}") from exc


def _as_records(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        for key in ("hypotheses", "records", "candidates", "results", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise GenerationUnavailable(f"expected a JSON list, got {type(payload).__name__}")
    bad = [type(x).__name__ for x in payload if not isinstance(x, dict)]
    if bad:
        raise GenerationUnavailable(f"list contained non-objects: {sorted(set(bad))}")
    return payload
