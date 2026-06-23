"""Halmos backend — symbolic counterexample search toward the break predicate.

Halmos symbolically executes a forge test with symbolic inputs and reports a
counterexample when the invariant assertion can be violated. It is forge-native,
so it runs against a `check_*` symbolic test that drives the protocol and
asserts the predicate.

Per-target symbolic harnesses are not yet generated (that is M4.5 — the same
synthesis step the gate's PoC needs), so on targets without one this backend
reports OUT_OF_SCOPE honestly while remaining AVAILABLE. This keeps the coverage
map truthful: the tool is wired and installed; the harness is the missing piece.

State label: PARTIAL (adapter wired; per-target symbolic harness synthesis pending).
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any

from .schema import PathResult, PathStatus

# Targets with a generated symbolic harness (none yet — synthesis is M4.5).
_HARNESSES: dict[tuple[str, str], str] = {}


class HalmosBackend:
    name = "halmos"

    def available(self) -> bool:
        return bool(shutil.which("halmos") and shutil.which("forge"))

    def find_path(self, hypothesis: Any, model: dict[str, Any],
                  repo_dir: Any | None = None, timeout: int = 120) -> PathResult:
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
            return done(status=PathStatus.UNAVAILABLE, notes="halmos/forge not on PATH")
        if (contract, fn) not in _HARNESSES or repo_dir is None:
            return done(status=PathStatus.OUT_OF_SCOPE,
                        notes="no symbolic harness for this target yet "
                              "(per-target symbolic harness synthesis is M4.5)")
        # (When a harness exists: write it, run `halmos --function check_* `,
        #  parse the counterexample. Left for M4.5.)
        return done(status=PathStatus.OUT_OF_SCOPE, notes="harness pending")
