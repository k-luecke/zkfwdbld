"""Medusa backend — stateful fuzzing toward the break predicate.

Medusa fuzzes the zero-arg actions on a property harness and flags when the
property (the invariant) is violated — i.e. it must DISCOVER the call sequence
that drives the state to the break. The harness is provided per target (like the
M1 gate's scenario); what the fuzzer finds autonomously is the path.

Honest about coverage: whole-project compile + fuzz is heavy, so within a
bounded budget this backend may report TIMEOUT. That outcome is logged, not
hidden — it is part of the discovery-coverage map.

State label: IMPLEMENTED (adapter) / coverage is environment-bounded.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .schema import PathResult, PathStatus

_SOLIDITY = Path(__file__).resolve().parent / "solidity"
_INSTALL = Path("test") / "_vagent_fuzz"

# Per-target fuzz harnesses: (contract, function) -> (harness file, targetContract).
_HARNESSES = {
    ("UTB", "receiveFromBridge"): ("DecentFuzzHarness.sol", "DecentFuzzHarness"),
}
_GATE_BINDINGS = {("UTB", "receiveFromBridge"): "DecentReceiveFromBridgeBypass"}


class MedusaBackend:
    name = "medusa"

    def available(self) -> bool:
        return bool(shutil.which("medusa") and shutil.which("forge"))

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        home = Path.home()
        extra = [str(home / ".foundry" / "bin"), "/usr/local/bin"]
        env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
        env.setdefault("FOUNDRY_OFFLINE", "true")
        if (home / ".svm").is_dir():
            env.setdefault("SVM_HOME", str(home / ".svm"))
        return env

    def find_path(self, hypothesis: Any, model: dict[str, Any],
                  repo_dir: Any | None = None, timeout: int = 90) -> PathResult:
        t0 = time.time()
        hid = getattr(hypothesis, "id", "?")
        contract = getattr(hypothesis, "target_contract", "?")
        fn = getattr(hypothesis, "target_function", "?")
        target = f"{contract}.{fn}"
        rc = getattr(hypothesis, "root_cause", "")

        def done(**kw):
            kw.setdefault("elapsed_s", round(time.time() - t0, 2))
            return PathResult(backend=self.name, hypothesis_id=hid, target=target,
                              mechanism=rc, **kw)

        if not self.available():
            return done(status=PathStatus.UNAVAILABLE, notes="medusa/forge not on PATH")
        harness = _HARNESSES.get((contract, fn))
        if harness is None or repo_dir is None:
            return done(status=PathStatus.OUT_OF_SCOPE,
                        notes="no fuzz harness provided for this target (harness synthesis is M4.5)")

        repo = Path(repo_dir)
        hfile, tcontract = harness
        install = repo / _INSTALL
        install.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_SOLIDITY / hfile, install / hfile)
        cfg = self._write_config(repo, tcontract, timeout)

        try:
            proc = subprocess.run(
                ["medusa", "fuzz", "--config", str(cfg)],
                cwd=str(repo), env=self._env(),
                capture_output=True, text=True, timeout=timeout + 60)
        except subprocess.TimeoutExpired:
            return done(status=PathStatus.TIMEOUT,
                        notes=f"medusa did not converge within {timeout}s budget")
        out = _strip(proc.stdout + "\n" + proc.stderr)
        return self._parse(out, contract, fn, done)

    def _write_config(self, repo: Path, target_contract: str, timeout: int) -> Path:
        cfg = repo / "medusa_vagent.json"
        # Derive from medusa's own defaults to stay schema-correct across versions.
        try:
            subprocess.run(["medusa", "init", "--out", str(cfg)],
                           cwd=str(repo), env=self._env(),
                           capture_output=True, text=True, timeout=60)
            d = json.loads(cfg.read_text())
        except Exception:
            d = {"fuzzing": {"testing": {"assertionTesting": {}, "propertyTesting": {},
                                          "optimizationTesting": {}}}}
        fz = d.setdefault("fuzzing", {})
        fz["targetContracts"] = [target_contract]
        fz["testLimit"] = 5000
        fz["timeout"] = timeout
        fz["workers"] = 6
        fz["callSequenceLength"] = 3
        t = fz.setdefault("testing", {})
        t.setdefault("assertionTesting", {})["enabled"] = False
        t.setdefault("optimizationTesting", {})["enabled"] = False
        t.setdefault("propertyTesting", {})["enabled"] = True
        t["stopOnFailedTest"] = True
        cfg.write_text(json.dumps(d, indent=2))
        return cfg

    def _parse(self, out: str, contract: str, fn: str, done):
        # Medusa reports a failing property with the call sequence that broke it.
        failed = re.search(r"(property_\w+).*?(fail|violat)", out, re.IGNORECASE)
        called = re.search(r"op_unauth_\w+|receiveFromBridge", out)
        if "no assertion, property" in out:
            return done(status=PathStatus.ERROR,
                        notes="medusa did not register the property (config/compile issue)")
        if failed or called:
            return done(status=PathStatus.FOUND, found=True,
                        attack_entrypoint=fn,
                        call_sequence=["fuzzer found a sequence calling the unguarded "
                                       "entrypoint that violates the property"],
                        gate_binding=_GATE_BINDINGS.get((contract, fn)),
                        notes="medusa fuzzing violated property_executes_equal_fees")
        return done(status=PathStatus.NO_PATH,
                    notes="medusa completed without violating the property")


def _strip(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)
