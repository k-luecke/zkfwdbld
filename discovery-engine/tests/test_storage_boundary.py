"""The storage boundary: git holds control state, Drive holds bulk bytes."""

from __future__ import annotations

import json
import os

import pytest

import paths


def test_put_control_lands_in_the_git_tree(isolated_roots):
    dest = paths.put_control("human_queue/x.json", {"a": 1})
    assert dest.is_relative_to(paths.state_root())
    assert json.loads(dest.read_text()) == {"a": 1}


def test_put_artifact_lands_in_drive_and_returns_only_a_pointer(isolated_roots):
    pointer = paths.put_artifact("nrr/10.1000-x.pdf", b"%PDF-1.7 bytes")
    assert pointer == "drive://nrr/10.1000-x.pdf"
    written = isolated_roots["drive"] / "nrr" / "10.1000-x.pdf"
    assert written.read_bytes() == b"%PDF-1.7 bytes"
    # the bytes must not appear anywhere under the git-tracked root
    assert not any(p.is_file() and p.suffix == ".pdf"
                   for p in paths.state_root().rglob("*"))


def test_put_artifact_leaves_no_temp_files_behind(isolated_roots):
    paths.put_artifact("nrr/a.pdf", b"x")
    leftovers = [p.name for p in (isolated_roots["drive"] / "nrr").iterdir()
                 if p.name != "a.pdf"]
    assert leftovers == [], f"a sync daemon would pick these up: {leftovers}"


def test_put_artifact_refuses_to_put_bulk_bytes_in_the_git_tree(monkeypatch, isolated_roots):
    monkeypatch.setenv("DRIVE_DIR", str(paths.state_root() / "sneaky"))
    with pytest.raises(paths.StorageBoundaryError):
        paths.put_artifact("big.h5", b"0" * 1024)


def test_targets_schema_is_repo_to_tags(isolated_roots):
    paths.targets_file().write_text(json.dumps({"/repo/a": ["bridge", "nonce"]}))
    assert paths.load_targets() == {"/repo/a": ["bridge", "nonce"]}
    paths.targets_file().write_text("[]")
    with pytest.raises(ValueError):
        paths.load_targets()


def test_missing_targets_file_is_empty_not_an_error(isolated_roots):
    if paths.targets_file().exists():
        os.unlink(paths.targets_file())
    assert paths.load_targets() == {}
