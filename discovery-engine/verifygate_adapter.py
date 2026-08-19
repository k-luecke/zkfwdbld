#!/usr/bin/env python3
"""verifygate_adapter.py — the real seam to the VerifyGate four-phase harness.

This replaces the `_run_verifygate` TODO with a call into the actual
`verification_agent.verify` harness that lives next door in this repo:
baseline -> control -> attack -> recheck, verdict emitted ON-CHAIN by
VerifyGate.sol and merely parsed in Python.

THREE HONEST BOUNDARIES, all enforced here rather than papered over:

1. The harness's rich verdict taxonomy is preserved, then projected onto the
   three words the orchestration layer speaks:
       CONFIRMED                -> CONFIRMED
       REJECTED_* (any reason)  -> REFUTED
       NO_VERDICT               -> INCONCLUSIVE
   The original verdict rides along in `raw_verdict`, so nothing is destroyed —
   "rejected because the attack reverted" and "rejected because the predicate
   was brittle" are different facts and stay different in the record.

2. A hypothesis is NOT a runnable case. The gate judges compiled Solidity: it
   needs a target Foundry checkout and a case contract (that is what M4.5
   scenario synthesis produces). A hypothesis that carries no scenario gets
   INCONCLUSIVE with reason `no_runnable_case` — never CONFIRMED, and never
   silently dropped as if it had been tested.

3. When the prerequisites are missing (no harness, no forge, no target), the
   result is `available=False` + INCONCLUSIVE. An unavailable oracle is a fact
   about this machine, and the run report counts it in its own column so it can
   never be mistaken for a lane that ran and found nothing.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import shutil
import sys

_HERE = pathlib.Path(__file__).resolve().parent

# The orchestration layer's three-word vocabulary.
CONFIRMED = "CONFIRMED"
REFUTED = "REFUTED"
INCONCLUSIVE = "INCONCLUSIVE"


@dataclasses.dataclass(frozen=True)
class GateResult:
    verdict: str                 # CONFIRMED | REFUTED | INCONCLUSIVE
    reason: str                  # why, in machine-greppable form
    available: bool              # did the gate actually execute?
    raw_verdict: str = ""        # the harness's own verdict, undiluted
    predicate: str = ""          # the invariant the gate judged
    detail: str = ""             # human-readable note / error tail

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def va_repo() -> pathlib.Path:
    """Where the verification-agent package lives. VA_REPO overrides."""
    env = os.environ.get("VA_REPO")
    if env:
        return pathlib.Path(env).expanduser()
    return _HERE.parent / "verification-agent"


def forge_path() -> str | None:
    """forge on PATH, or the standard foundryup location the harness also checks."""
    found = shutil.which("forge")
    if found:
        return found
    candidate = pathlib.Path.home() / ".foundry" / "bin" / "forge"
    return str(candidate) if candidate.is_file() else None


def preflight() -> list[str]:
    """Everything the gate needs and does not have, in one list. Empty == ready."""
    missing: list[str] = []
    if not (va_repo() / "verification_agent" / "verify" / "harness.py").is_file():
        missing.append(f"verification_agent package not found under {va_repo()}")
    elif _import_harness() is None:
        missing.append("verification_agent.verify could not be imported")
    if forge_path() is None:
        missing.append("forge (Foundry) not installed — the gate fork-executes Solidity")
    return missing


def _import_harness():
    """Import the harness lazily; returns the module or None."""
    root = str(va_repo())
    if (va_repo() / "verification_agent").is_dir() and root not in sys.path:
        sys.path.insert(0, root)
    try:
        from verification_agent.verify import harness  # noqa: PLC0415
        return harness
    except Exception:                                   # noqa: BLE001
        return None


def _project(raw: str) -> tuple[str, str]:
    """Harness verdict -> (orchestration verdict, reason)."""
    if raw == "CONFIRMED":
        return CONFIRMED, "gate_confirmed"
    if raw.startswith("REJECTED_"):
        return REFUTED, raw.lower()
    return INCONCLUSIVE, "no_verdict_marker"


# --------------------------------------------------------------- the gate call
def verify(hypothesis: dict, *, timeout: int = 900) -> GateResult:
    """Run one hypothesis's scenario through the unchanged four-phase gate.

    The hypothesis must carry a runnable scenario:
        target_repo    path to a Foundry checkout the case compiles against
        contract_name  the case contract (forge --match-contract)
    Optional: case_id, scenario_sol (extra .sol installed beside the gate).
    """
    target = hypothesis.get("target_repo") or hypothesis.get("target")
    contract = hypothesis.get("contract_name")
    if not target or not contract:
        return GateResult(
            INCONCLUSIVE, "no_runnable_case", available=False,
            detail=("hypothesis carries no gate scenario (needs target_repo + "
                    "contract_name); M4.5 synthesis turns a lead into one"))

    missing = preflight()
    if missing:
        return GateResult(INCONCLUSIVE, "oracle_unavailable", available=False,
                          detail="; ".join(missing))

    target_dir = pathlib.Path(str(target)).expanduser()
    if not target_dir.is_dir():
        return GateResult(INCONCLUSIVE, "target_missing", available=False,
                          detail=f"{target_dir} is not a directory")

    harness_mod = _import_harness()
    from verification_agent.verify.case import CaseKind, VerificationCase
    from verification_agent.verify.gate import Verdict

    case = VerificationCase(
        case_id=str(hypothesis.get("case_id") or hypothesis.get("id") or contract),
        contract_name=str(contract),
        kind=CaseKind.KNOWN_TRUE,
        hypothesis=str(hypothesis.get("hypothesis") or hypothesis.get("claim") or ""),
        expected_verdict=Verdict.CONFIRMED,
        source_finding=str(hypothesis.get("source_finding") or "moe surfacer"),
    )
    extra = [pathlib.Path(p).expanduser() for p in hypothesis.get("scenario_sol", [])]

    runner = harness_mod.VerifyHarness(target_dir)
    try:
        runner.install_templates(extra_sol=extra or None)
        result = runner.run_case(case, timeout=timeout)
    except Exception as exc:                            # noqa: BLE001
        return GateResult(INCONCLUSIVE, "gate_execution_error", available=False,
                          detail=f"{type(exc).__name__}: {exc}"[:400])
    finally:
        runner.cleanup()

    verdict, reason = _project(result.verdict.value)
    return GateResult(verdict, reason, available=True,
                      raw_verdict=result.verdict.value,
                      predicate=result.predicate_text,
                      detail=result.verdict.explanation)


# ------------------------------------------------------------- the smoke test
def selftest(target_repo: str | pathlib.Path, *, timeout: int = 900) -> dict:
    """Run the M1 self-proof registry — the smoke test for this lane.

    The registry's known-true case is a real judged finding (Code4rena
    2024-01-decent M-03); the others are constructed controls the gate must
    REJECT. A gate that confirms the real one and rejects all four controls is
    working; anything else means do not trust tonight's run.

    Needs forge and a 2024-01-decent checkout, so it runs on the compute host,
    not in a container without Foundry.
    """
    missing = preflight()
    if missing:
        return {"ok": False, "reason": "oracle_unavailable", "missing": missing}

    harness_mod = _import_harness()
    from verification_agent.verify.cases import DECENT_M1_CASES

    runner = harness_mod.VerifyHarness(pathlib.Path(str(target_repo)).expanduser())
    results = runner.run_suite(DECENT_M1_CASES)
    rows = [r.to_record() for r in results]
    return {
        "ok": all(r["gate_correct"] for r in rows),
        "cases": rows,
        "known_true_confirmed": any(
            r["kind"] == "known_true" and r["verdict"] == "CONFIRMED" for r in rows),
    }
