"""Assemble the TargetModel: clone -> build -> Slither -> surface tagging.

This is the M0 entry point used by the CLI. It is deliberately linear and
swappable: each stage returns data, the builder stitches it into a
``TargetModel``, and every external-tool outcome is recorded in ``tool_status``
so the JSON is self-describing about how much to trust it.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from pathlib import Path

from ..ingest.build import (
    compile_project,
    detect_build_system,
    foundry_root,
    solc_version,
)
from ..ingest.clone import clone_repo, resolved_commit
from ..schema import TargetModel, ToolStatus
from . import lite, slither_runner


def build_model(
    repo_url: str,
    commit: str | None,
    workdir: Path,
    local_path: Path | None = None,
) -> TargetModel:
    """Build the model for a target.

    ``local_path`` lets callers point at an already-checked-out tree (used by
    tests and offline demos) instead of cloning.
    """
    notes: list[str] = []
    tool_status: list[ToolStatus] = []

    if local_path is not None:
        repo_dir = Path(local_path)
        notes.append(f"using local path {repo_dir} (no clone)")
    else:
        repo_dir = clone_repo(repo_url, commit, Path(workdir) / "repo")

    resolved = resolved_commit(repo_dir) or commit

    build_system = detect_build_system(repo_dir)
    build_result = compile_project(repo_dir, build_system)
    tool_status.append(ToolStatus(
        name=build_system if build_system != "unknown" else "build",
        available=build_result.compiled or "not installed" not in build_result.detail,
        ran=build_result.compiled,
        version=build_result.version,
        detail=build_result.detail,
    ))
    notes.append(f"build: {build_result.detail}")

    # Stamp the solidity compiler version so a run is reproducible against a
    # known toolchain. Captured independently of forge — solc-select switches
    # are global state and worth recording in the model itself.
    sv = solc_version()
    tool_status.append(ToolStatus(
        name="solc", available=sv is not None, ran=False,
        version=sv,
        detail="version captured (compiler invoked by forge, not directly)"
               if sv else "solc not on PATH"))

    model = TargetModel(
        repo_url=repo_url,
        commit=resolved,
        build_system=build_system,
        compiled=build_result.compiled,
        tool_status=tool_status,
        notes=notes,
    )

    # Primary path: Slither over the compiled project.
    target = foundry_root(repo_dir) if build_system == "foundry" else repo_dir
    used_slither = False
    if slither_runner.slither_available():
        try:
            extract = slither_runner.run_slither(target)
            model.contracts = extract.contracts
            model.storage_layout = extract.storage_layout
            model.entry_points = extract.entry_points
            model.call_graph = extract.call_graph
            tool_status.append(ToolStatus(
                name="slither", available=True, ran=True,
                version=extract.version, detail="extracted structural model"))
            used_slither = True
        except Exception as exc:  # noqa: BLE001 - record, then degrade
            tool_status.append(ToolStatus(
                name="slither", available=True, ran=False,
                detail=f"slither failed: {type(exc).__name__}: {exc}"))
            notes.append("slither failed; falling back to regex-lite extractor")
    else:
        tool_status.append(ToolStatus(
            name="slither", available=False, ran=False,
            detail="slither not importable"))

    if not used_slither:
        sol_files = _solidity_sources(repo_dir)
        contracts, storage, entry_points = lite.extract_lite(sol_files)
        model.contracts = contracts
        model.storage_layout = storage
        model.entry_points = entry_points
        model.notes.append(
            "DEGRADED MODEL: built from regex-lite extractor, not Slither. "
            "Call graph and storage slots are incomplete. Do not treat as "
            "ground truth.")

    # The headline output: priority verification surface = tagged entry points.
    model.verification_surface = [f for f in model.entry_points if f.surfaces]
    model.notes.append(
        f"verification surface: {len(model.verification_surface)} of "
        f"{len(model.entry_points)} entry points tagged priority")
    return model


def _solidity_sources(repo_dir: Path) -> list[Path]:
    repo_dir = Path(repo_dir)
    skip = ("/lib/", "/node_modules/", "/test/", "/tests/", "/script/",
            "/out/", "/cache/")
    files: list[Path] = []
    for p in repo_dir.rglob("*.sol"):
        sp = str(p).replace("\\", "/")
        if any(s in sp for s in skip):
            continue
        files.append(p)
    return files
