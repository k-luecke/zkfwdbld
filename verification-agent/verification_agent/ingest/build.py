"""Build-system detection and compilation.

Foundry is first-class; Hardhat is a fallback. We do not write a Solidity
parser or a build system — we drive the project's own.

State label: IMPLEMENTED (Foundry path), PARTIAL (Hardhat path — detected and
compiled, but downstream modeling is tuned for Foundry layouts).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BuildResult:
    build_system: str  # foundry | hardhat | unknown
    compiled: bool
    detail: str
    version: str | None = None  # build tool's own version, for run-artifact stamping


def detect_build_system(repo_dir: Path) -> str:
    repo_dir = Path(repo_dir)
    if (repo_dir / "foundry.toml").exists():
        return "foundry"
    # Some monorepos nest the Foundry project; check one level down.
    for child in repo_dir.iterdir() if repo_dir.exists() else []:
        if child.is_dir() and (child / "foundry.toml").exists():
            return "foundry"
    if any((repo_dir / f).exists() for f in (
        "hardhat.config.js", "hardhat.config.ts")):
        return "hardhat"
    return "unknown"


def foundry_root(repo_dir: Path) -> Path:
    """Return the directory containing foundry.toml (repo root or one nested)."""
    repo_dir = Path(repo_dir)
    if (repo_dir / "foundry.toml").exists():
        return repo_dir
    for child in sorted(repo_dir.iterdir()):
        if child.is_dir() and (child / "foundry.toml").exists():
            return child
    return repo_dir


def compile_project(repo_dir: Path, build_system: str) -> BuildResult:
    repo_dir = Path(repo_dir)
    if build_system == "foundry":
        root = foundry_root(repo_dir)
        if not _which("forge"):
            return BuildResult("foundry", False,
                               "forge not installed; skipped compilation")
        proc = subprocess.run(
            ["forge", "build", "--skip", "test", "--skip", "script"],
            cwd=str(root), capture_output=True, text=True)
        ok = proc.returncode == 0
        detail = "forge build ok" if ok else f"forge build failed: {proc.stderr.strip()[:500]}"
        return BuildResult("foundry", ok, detail, version=forge_version())

    if build_system == "hardhat":
        if not _which("npx"):
            return BuildResult("hardhat", False, "npx not available")
        # Install + compile is heavy; we attempt compile only.
        proc = subprocess.run(["npx", "hardhat", "compile"],
                              cwd=str(repo_dir), capture_output=True, text=True)
        ok = proc.returncode == 0
        return BuildResult("hardhat", ok,
                           "hardhat compile ok" if ok else proc.stderr.strip()[:500])

    return BuildResult("unknown", False, "no recognized build system")


def forge_version() -> str | None:
    """Capture forge's reported version (first line, after 'Version: ').
    Stamped into the run artifact so a Sequence number is attributable to
    a known toolchain — slither >= 0.10 already taught us that a silent
    upstream behavior change can corrupt the call graph."""
    if not _which("forge"):
        return None
    try:
        proc = subprocess.run(["forge", "--version"], capture_output=True,
                              text=True, timeout=10)
    except (subprocess.TimeoutExpired, OSError):
        return None
    line = (proc.stdout or "").splitlines()[0].strip() if proc.stdout else ""
    if line.lower().startswith("forge version:"):
        return line.split(":", 1)[1].strip()
    return line or None


def solc_version() -> str | None:
    """Capture solc's semver (e.g. '0.8.20' from 'Version: 0.8.20+commit...').
    None when solc isn't on PATH, so the absence is visible in tool_status
    rather than silently degraded."""
    if not _which("solc"):
        return None
    try:
        proc = subprocess.run(["solc", "--version"], capture_output=True,
                              text=True, timeout=10)
    except (subprocess.TimeoutExpired, OSError):
        return None
    for line in (proc.stdout or "").splitlines():
        s = line.strip()
        if s.lower().startswith("version:"):
            v = s.split(":", 1)[1].strip()
            return v.split("+", 1)[0] if "+" in v else v
    return None


def _which(prog: str) -> bool:
    from shutil import which
    return which(prog) is not None
