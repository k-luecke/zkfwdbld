"""Verify harness — compile + fork-execute a PoC and read the gate's verdict.

This is the differentiator. It installs the Solidity gate templates into a
target Foundry repo, runs each case with `forge test`, and parses the
on-chain-emitted verdict. The verdict is decided on-chain (VerifyGate.sol); this
module only orchestrates and reports.

State label: IMPLEMENTED.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .case import VerificationCase
from .gate import Verdict, parse_verdict

_SOLIDITY_DIR = Path(__file__).resolve().parent / "solidity"
_INSTALL_SUBDIR = Path("test") / "_vagent"


@dataclass
class CaseResult:
    case: VerificationCase
    verdict: Verdict
    expected: Verdict
    gate_correct: bool          # did the gate return the expected verdict?
    raw_output: str

    @property
    def confirmed(self) -> bool:
        return self.verdict.is_confirmed


def _foundry_env() -> dict[str, str]:
    """Environment that lets forge find a pre-staged, offline solc.

    Where the public Solidity binary host is blocked, solc binaries are staged
    under ~/.svm and Foundry runs offline. We prepend ~/.foundry/bin so forge is
    found without requiring it on the caller's PATH.
    """
    env = dict(os.environ)
    home = Path.home()
    foundry_bin = home / ".foundry" / "bin"
    if foundry_bin.is_dir():
        env["PATH"] = f"{foundry_bin}{os.pathsep}{env.get('PATH', '')}"
    env.setdefault("FOUNDRY_OFFLINE", "true")
    svm = home / ".svm"
    if svm.is_dir():
        env.setdefault("SVM_HOME", str(svm))
    return env


class VerifyHarness:
    """Runs verification cases against one cloned Foundry target."""

    def __init__(self, repo_dir: Path):
        self.repo_dir = Path(repo_dir)
        if not (self.repo_dir / "foundry.toml").exists():
            # Allow a nested foundry root.
            for child in sorted(self.repo_dir.iterdir()):
                if child.is_dir() and (child / "foundry.toml").exists():
                    self.repo_dir = child
                    break
        self.install_dir = self.repo_dir / _INSTALL_SUBDIR

    def install_templates(self, extra_sol: list[Path] | None = None) -> None:
        self.install_dir.mkdir(parents=True, exist_ok=True)
        for sol in _SOLIDITY_DIR.glob("*.sol"):
            shutil.copy2(sol, self.install_dir / sol.name)
        for sol in extra_sol or []:
            shutil.copy2(sol, self.install_dir / Path(sol).name)

    def cleanup(self) -> None:
        if self.install_dir.exists():
            shutil.rmtree(self.install_dir, ignore_errors=True)

    def run_case(self, case: VerificationCase, timeout: int = 300) -> CaseResult:
        proc = subprocess.run(
            ["forge", "test",
             "--match-contract", case.contract_name,
             "--match-test", "testGate",
             "-vv"],
            cwd=str(self.repo_dir),
            env=_foundry_env(),
            capture_output=True, text=True, timeout=timeout,
        )
        output = proc.stdout + "\n" + proc.stderr
        verdict = parse_verdict(output)
        return CaseResult(
            case=case,
            verdict=verdict,
            expected=case.expected_verdict,
            gate_correct=(verdict == case.expected_verdict),
            raw_output=output,
        )

    def run_suite(
        self, cases: list[VerificationCase], install: bool = True
    ) -> list[CaseResult]:
        if install:
            self.install_templates()
        try:
            return [self.run_case(c) for c in cases]
        finally:
            if install:
                self.cleanup()
