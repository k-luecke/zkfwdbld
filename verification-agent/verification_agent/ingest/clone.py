"""Clone a scope repo at a pinned commit.

State label: IMPLEMENTED.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class CloneError(RuntimeError):
    pass


def clone_repo(repo_url: str, commit: str | None, dest: Path) -> Path:
    """Clone ``repo_url`` into ``dest`` and check out ``commit`` if given.

    Returns the path to the working tree. Pinning to a commit is mandatory for
    reproducible findings — a contest is judged at a fixed commit, so we never
    silently track a moving branch when a commit is supplied.
    """
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise CloneError(f"destination {dest} exists and is not empty")
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Shallow-ish clone: full history only if we must reach an arbitrary commit.
    _run(["git", "clone", "--quiet", repo_url, str(dest)])
    if commit:
        try:
            _run(["git", "-C", str(dest), "checkout", "--quiet", commit])
        except CloneError:
            # The commit may be unreachable from the default shallow clone;
            # fetch it explicitly then retry.
            _run(["git", "-C", str(dest), "fetch", "--quiet", "origin", commit])
            _run(["git", "-C", str(dest), "checkout", "--quiet", commit])

    # Pull submodules — Foundry deps (forge-std, openzeppelin, etc.) are almost
    # always submodules and the build fails without them.
    _run(["git", "-C", str(dest), "submodule", "update", "--init", "--recursive", "--quiet"],
         check=False)
    return dest


def resolved_commit(repo_dir: Path) -> str | None:
    try:
        out = _run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"])
        return out.strip()
    except CloneError:
        return None


def _run(cmd: list[str], check: bool = True) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise CloneError(f"{' '.join(cmd)} failed: {proc.stderr.strip()}")
    return proc.stdout
