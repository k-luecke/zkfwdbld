#!/usr/bin/env python3
"""paths.py — the storage boundary, in one place.

Two stores, split by what each backend is actually good at. Do not cross them.

    git tree  -> code + SMALL control state (queues, targets, verdicts). Text,
                 diffable, mergeable. This is the ONLY thing GitHub can review.
                 It is also the cross-device sync: the timer commits and pushes
                 it, so the phone and the browser see results.
    DRIVE_DIR -> BULK artifacts (paper corpora, extracted datasets, figures,
                 HDF5). Big, often binary, git-hostile.

The engine reaches Drive via rclone or Drive-for-Desktop pointed at DRIVE_DIR.
That is NOT the chat-side Drive connector — the connector lets Claude read the
Drive from the app; it gives the unattended machine nothing.

HARD RULE, enforced in code below: never write many small files live into a
Drive-synced folder. A timer firing mid-sync races the sync daemon and spawns
conflict copies ("results (1).json"). Control state stays in git; Drive receives
only FINISHED artifacts, written atomically.

Every path is resolved through a FUNCTION, not a module constant, so the
environment (and the tests) can move the roots without reimporting.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile

_HERE = pathlib.Path(__file__).resolve().parent


class StorageBoundaryError(RuntimeError):
    """Raised when a caller tries to put bulk bytes into the git tree."""


# ------------------------------------------------------------------ git side
def state_root() -> pathlib.Path:
    """Small control state. Tracked in git — this is the sync.

    Defaults to the repo's own `state/` dir, which is what makes the queues
    reviewable from a phone. Set MOE_ROOT to relocate (e.g. ~/moe on a host
    where the repo is cloned elsewhere).
    """
    return pathlib.Path(os.environ.get("MOE_ROOT", str(_HERE / "state"))).expanduser()


def q_review() -> pathlib.Path:
    """Gate-passed items awaiting a human acceptance decision."""
    return state_root() / "human_queue"


def q_drafts() -> pathlib.Path:
    """Proposed riddles awaiting human floor-validation."""
    return state_root() / "riddle_drafts"


def q_refused() -> pathlib.Path:
    """Lanes the engine declined to run, with reasons. Visible on purpose."""
    return state_root() / "refused_log"


def targets_file() -> pathlib.Path:
    """{repo_path: [surface_tags]} — appended to during the workday."""
    return state_root() / "targets.json"


def ensure_dirs() -> None:
    """Create the control dirs. Called by the CLI, never at import time."""
    for d in (q_review(), q_drafts(), q_refused()):
        d.mkdir(parents=True, exist_ok=True)


def load_targets() -> dict[str, list[str]]:
    f = targets_file()
    if not f.exists():
        return {}
    data = json.loads(f.read_text() or "{}")
    if not isinstance(data, dict):
        raise ValueError(f"{f} must be an object of {{repo_path: [surface_tags]}}")
    return {k: list(v) for k, v in data.items()}


def put_control(rel_path: str, payload: dict) -> pathlib.Path:
    """Small control/queue state -> git tree. Committed & pushed by the timer."""
    dest = state_root() / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return dest


# ---------------------------------------------------------------- drive side
def drive_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("DRIVE_DIR", "~/drive/moe")).expanduser()


def put_artifact(rel_path: str, data: bytes) -> str:
    """Bulk artifact -> DRIVE_DIR, atomically. Returns a drive:// pointer.

    Atomic because a sync daemon must never observe a half-written file: write a
    temp file in the destination directory, then os.replace it into place. The
    git side stores the POINTER this returns, never the bytes.
    """
    dest = (drive_dir() / rel_path).resolve()
    root = drive_dir().resolve()
    if root == state_root().resolve() or _is_within(dest, state_root().resolve()):
        raise StorageBoundaryError(
            f"refusing to write bulk bytes into the git tree ({dest}); "
            "set DRIVE_DIR to a Drive-backed path outside the repo")
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)          # atomic within one filesystem
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return f"drive://{rel_path}"


def _is_within(child: pathlib.Path, parent: pathlib.Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True
