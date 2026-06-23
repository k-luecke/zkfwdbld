"""M4.5 synthesis runner — run a synthesized scenario through the UNCHANGED gate.

This is where the no-fast-path discipline lives. A machine-synthesized scenario
gets exactly the same treatment as a hand-built M1 case: it is dropped next to
the real `VerifyGate.sol` and judged by the same four-phase `testGate`. The gate
does not know (or care) whether a human or the synthesizer wrote the scenario —
which is precisely what keeps machine-written scenarios honest.

The runner copies the byte-for-byte real `VerifyGate.sol` from `verify/solidity/`
(not a reimplementation), so "the same gate" is literally true.

State label: IMPLEMENTED. Requires forge + a workspace with forge-std (the
self-contained scenario generates its own target, so no protocol clone is needed).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..verify.gate import Verdict, parse_markers
from ..verify.harness import _foundry_env
from .schema import SynthCase, SynthScenario

_GATE_SOL = (Path(__file__).resolve().parents[1]
             / "verify" / "solidity" / "VerifyGate.sol")
_INSTALL_SUBDIR = Path("test") / "_vagent"

_FOUNDRY_TOML = """[profile.default]
src = "src"
test = "test"
libs = ["lib"]
solc = "0.8.25"
remappings = ["forge-std/=lib/forge-std/src/"]
"""


@dataclass
class SynthResult:
    case: SynthCase
    verdict: Verdict
    expected: Verdict
    gate_correct: bool
    predicate_text: str = ""

    def to_dict(self) -> dict:
        return {
            "contract": self.case.contract_name,
            "role": self.case.role,
            "case_id": self.case.case_id,
            "expected_verdict": self.expected.value,
            "verdict": self.verdict.value,
            "gate_correct": self.gate_correct,
            "predicate": self.predicate_text,
        }


class SynthesisRunner:
    """Fork-executes a synthesized scenario through the real verify gate."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.install_dir = self.workspace / _INSTALL_SUBDIR

    # -- workspace provisioning -------------------------------------------
    def ensure_workspace(self, forge_std: Path | None = None) -> None:
        """Create a minimal Foundry project (foundry.toml + lib/forge-std)."""
        (self.workspace / "src").mkdir(parents=True, exist_ok=True)
        (self.workspace / "test").mkdir(parents=True, exist_ok=True)
        (self.workspace / "lib").mkdir(parents=True, exist_ok=True)
        toml = self.workspace / "foundry.toml"
        if not toml.exists():
            toml.write_text(_FOUNDRY_TOML)
        dest = self.workspace / "lib" / "forge-std"
        if not (dest / "src").is_dir():
            if forge_std and (Path(forge_std) / "src").is_dir():
                shutil.copytree(forge_std, dest, dirs_exist_ok=True)
            else:
                self._clone_forge_std(dest)

    @staticmethod
    def _clone_forge_std(dest: Path) -> None:
        # Look for an existing checkout first (offline-friendly), else clone.
        for cand in Path("/home/user").glob("*/lib/forge-std"):
            if (cand / "src").is_dir():
                shutil.copytree(cand, dest, dirs_exist_ok=True)
                return
        subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", "v1.9.4",
             "https://github.com/foundry-rs/forge-std", str(dest)],
            check=True, capture_output=True, text=True, timeout=120,
        )

    # -- run ---------------------------------------------------------------
    def run(self, scenario: SynthScenario, timeout: int = 300) -> list[SynthResult]:
        if not scenario.executable:
            return []
        self.install_dir.mkdir(parents=True, exist_ok=True)
        # The SAME gate, byte-for-byte.
        shutil.copy2(_GATE_SOL, self.install_dir / "VerifyGate.sol")
        sol = self.install_dir / f"Synth_{_safe(scenario.lead_entrypoint)}.t.sol"
        sol.write_text(scenario.solidity)
        try:
            return [self._run_case(c, timeout) for c in scenario.cases]
        finally:
            shutil.rmtree(self.install_dir, ignore_errors=True)

    def _run_case(self, case: SynthCase, timeout: int) -> SynthResult:
        proc = subprocess.run(
            ["forge", "test", "--match-contract", case.contract_name,
             "--match-test", "testGate", "-vv"],
            cwd=str(self.workspace), env=_foundry_env(),
            capture_output=True, text=True, timeout=timeout,
        )
        verdict, predicate, _ = parse_markers(proc.stdout + "\n" + proc.stderr)
        expected = Verdict(case.expected_verdict)
        return SynthResult(
            case=case, verdict=verdict, expected=expected,
            gate_correct=(verdict == expected), predicate_text=predicate,
        )


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in (name or "scenario"))
