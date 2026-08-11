"""Test fixtures — every test runs against throwaway roots, never your real queues."""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated_roots(tmp_path, monkeypatch):
    """Point the git-side state root and the Drive side at tmp dirs.

    Autouse because a test that accidentally wrote into the tracked state/ dir
    would commit fake queue items — exactly the kind of thing this repo exists to
    prevent.
    """
    state = tmp_path / "state"
    drive = tmp_path / "drive"
    monkeypatch.setenv("MOE_ROOT", str(state))
    monkeypatch.setenv("DRIVE_DIR", str(drive))
    import paths
    paths.ensure_dirs()
    return {"state": state, "drive": drive}
