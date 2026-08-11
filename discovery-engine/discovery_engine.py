#!/usr/bin/env python3
"""discovery_engine.py — one registry, many lanes, running constantly without you.

Composes with moe_orchestrator.py (the contract-verification primitives) and adds
the layer around it: scientific studies actively found, executed, and audited
unattended, ALONGSIDE the verification work, with a human touching only the two
steps that structurally cannot be automated.

THE ONE INVARIANT, MADE EXECUTABLE:
    A lane may run unattended IFF it is human-validated AND has a machine-checkable
    oracle. Everything else is refused and logged — never faked. The refusal is a
    feature; do not remove it.

THE SECOND INVARIANT (the one that makes the first one true in practice):
    An oracle that could not RUN does not get to say PASS. A missing oracle
    produces INCONCLUSIVE plus a reason, counted in its own column of the run
    report. "Nothing found" and "nothing ran" must never look alike.

THE TWO HUMAN TOUCHPOINTS (both review, never build):
    1. Contract re-audit        — three-field bidirectional, on human_queue
    2. Riddle floor-validation  — four-corners/ceiling/floor form, on riddle_drafts
    Validate a riddle ONCE (an afternoon). From then on its lane runs forever.
"""

from __future__ import annotations

import dataclasses
import datetime
from typing import Callable, Optional

import paths
import verifygate_adapter as vg
# contract-lane primitives
from moe_orchestrator import (BLIND_PRECISION, CALIBRATION_EVENT,
                              REAUDIT_CHECKLIST)
from moe_orchestrator import gate as cc_gate
from moe_orchestrator import route as cc_route
from moe_orchestrator import surface as cc_surface
from headless import GenerationUnavailable, run_claude_json
# the storage boundary lives in paths.py; re-exported so callers have one import
from paths import put_artifact, put_control  # noqa: F401

PASS, FAIL = "PASS", "FAIL"
CONFIRMED, REFUTED, INCONCLUSIVE = vg.CONFIRMED, vg.REFUTED, vg.INCONCLUSIVE
ACCEPTING = (CONFIRMED, PASS)          # the only verdicts that reach a human


# ============================================================ oracles
# An oracle returns a verdict the generator CANNOT argue with. If a lane has no
# oracle, it cannot run unattended — by construction, not by policy.

@dataclasses.dataclass(frozen=True)
class Judgement:
    """A verdict plus the evidence for it. The detail is what a human spot-checks."""
    verdict: str
    detail: dict = dataclasses.field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.verdict in ACCEPTING

    @property
    def oracle_ran(self) -> bool:
        """False when the verdict reflects a missing oracle, not a judged candidate."""
        return bool(self.detail.get("oracle_ran", True))


def verifygate_oracle(candidate: dict) -> Judgement:
    """Fork-executed PoC: baseline -> control -> attack -> recheck. Binary truth."""
    judged = cc_gate(candidate)            # strips the generator's vote first
    return Judgement(judged["gate_verdict"], {
        "oracle": "verifygate_four_phase",
        "oracle_ran": judged["gate_available"],
        "reason": judged["gate_reason"],
        "raw_verdict": judged["gate_raw_verdict"],
        "predicate": judged["gate_predicate"],
        "note": judged["gate_detail"],
    })


ANDERSEN_CONTROLS = (
    "isotope_15N2_control",                   # 15N2 labeling with quantified crossover
    "open_circuit_blank",                     # NH3 at OCV subtracted
    "quantitative_NH3_method",                # calibrated (ISE/NMR/colorimetry)
    "rate_normalized_and_faradaic_efficiency",
    "gas_purification_reported",              # NOx/NH3 scrubbing upstream
)


def andersen2019_rubric(paper_fields: dict) -> Judgement:
    """Study 001 oracle. Andersen et al. 2019 (Nature) contamination-control rubric.

    MATURITY: PRESENCE FLOOR. This checks that each control is REPORTED, not that
    it clears a quantitative bar (quantified crossover, blank actually subtracted,
    method calibrated). Graded scoring is Prompt 2's job and needs the paper's
    thresholds in hand — inventing bars here would be guessing, which is the
    failure mode this engine exists to avoid. Every record says PRESENCE_FLOOR so
    a PASS is never read as more than it is.
    """
    present = {c: bool(paper_fields.get(c)) for c in ANDERSEN_CONTROLS}
    missing = [c for c, ok in present.items() if not ok]
    return Judgement(PASS if not missing else FAIL, {
        "oracle": "andersen2019_contamination_rubric",
        "oracle_maturity": "PRESENCE_FLOOR",
        "controls_present": present,
        "controls_missing": missing,
        "human_check": "confirm each present control is QUANTIFIED, not just named",
    })


def held_out_adversary_oracle(probe_result: dict) -> Judgement:
    """Study 002 oracle (Riddle VII). A deception probe passes only if it survives a
    model trained AGAINST the probe's readout. Abort condition baked in: if the
    adversary was not actually held out, the run is INCONCLUSIVE, not PASS.
    """
    if not probe_result.get("adversary_truly_held_out"):
        return Judgement(INCONCLUSIVE, {                # honest abort, not a fake pass
            "oracle": "held_out_adversary",
            "oracle_ran": False,
            "reason": "adversary_not_held_out",
        })
    auroc = probe_result.get("auroc_vs_adversary", 0)
    threshold = probe_result.get("threshold", 1)
    return Judgement(PASS if auroc > threshold else FAIL, {
        "oracle": "held_out_adversary",
        "auroc_vs_adversary": auroc,
        "threshold": threshold,
    })


# ============================================================ the lane
@dataclasses.dataclass
class Lane:
    name: str
    kind: str                                     # "verification" | "science"
    validated: bool                               # has a HUMAN confirmed the floor is real?
    oracle: Optional[Callable[[dict], Judgement]] # None => cannot run unattended
    generate: Callable[[], list[dict]]            # headless expert / paper puller
    note: str                                     # the honesty field, on every output
    preflight: Optional[Callable[[], list[str]]] = None   # unmet prerequisites

    @property
    def eligible(self) -> bool:
        """The invariant. Both conditions required. No exceptions, no override flag."""
        return self.validated and self.oracle is not None

    def unmet(self) -> list[str]:
        return list(self.preflight()) if self.preflight else []


# ============================================================ generators
def gen_contract_targets() -> list[dict]:
    """Overnight contract surfacing across the target list, routed by surface-tag."""
    out: list[dict] = []
    for target, tags in paths.load_targets().items():
        expert = cc_route(tags)
        if expert:
            out += cc_surface(expert, target)["hypotheses"]
    return out


def gen_nrr_papers() -> list[dict]:
    """Study 001 generator: pull recent electrocatalytic-NH3 papers and extract the
    fields the Andersen rubric scores. The extractor PROPOSES fields; the rubric
    judges. TODO(prompt 2): wire the literature source (arXiv + Crossref).

    Storage split in action: the PDF corpus (bulk) goes to Drive; only the
    extracted fields + a drive:// pointer (small) ride the git tree into the rubric.
    """
    prompt = ("Extract Andersen-2019 contamination-control fields as a JSON list, "
              "one object per recent electrocatalytic nitrogen-reduction paper, "
              f"with these keys: {list(ANDERSEN_CONTROLS)} plus doi and title. "
              "Report presence/absence ONLY; do not judge whether a paper passes.")
    records = run_claude_json(prompt, model="sonnet",
                              tools="Read,Grep,Bash,WebSearch")
    for rec in records:
        if pdf := rec.pop("_pdf_bytes", None):    # extractor hands back raw bytes
            rec["corpus_pointer"] = put_artifact(
                f"nrr/{rec.get('doi', 'paper')}.pdf",
                pdf if isinstance(pdf, bytes) else str(pdf).encode())
    return records                                 # small records only, git-safe


def gen_deception_probes() -> list[dict]:
    """Study 002 generator: run probe candidates and report robustness fields."""
    return run_claude_json(
        "Run deception-probe candidates; report auroc_vs_adversary, threshold, and "
        "adversary_truly_held_out as a JSON list.",
        model="opus", tools="Read,Grep,Bash,WebSearch")


# ============================================================ the registry
class Registry:
    def __init__(self) -> None:
        self._lanes: list[Lane] = []

    def register(self, lane: Lane) -> None:
        self._lanes.append(lane)

    def all(self) -> list[Lane]:
        return list(self._lanes)

    def eligible(self) -> list[Lane]:
        return [l for l in self._lanes if l.eligible]

    def refused(self) -> list[Lane]:
        return [l for l in self._lanes if not l.eligible]


# The refused riddles are REGISTERED, not omitted — the engine must know they are
# real riddles it is deliberately declining to fake. validated=True (they ARE open
# problems) but oracle=None (their floor is a theorem/epistemic wall). eligible=False.
REFUSED_RIDDLES = [
    Lane("I_bedside_witness",  "science", True, None, lambda: [],
         "NO ORACLE: floor = you can never verify a negative. Human judgment only."),
    Lane("II_quantum_gravity", "science", True, None, lambda: [],
         "NO ORACLE: floor = LOCC; the open part is an inference, not a checkable event."),
    Lane("VIII_biosignatures", "science", True, None, lambda: [],
         "NO ORACLE: floor = n=1, no ground truth. More telescope time doesn't move it."),
]


def build_registry() -> Registry:
    r = Registry()
    # verification work — runs constantly, oracle = fork-executed PoC
    r.register(Lane("contract_verification", "verification", True, verifygate_oracle,
                    gen_contract_targets, "ORACLE: VerifyGate four-phase PoC.",
                    preflight=vg.preflight))
    # Study 001 — the FIRST registered science lane, proving the registry works.
    # It is not the point; it is the proof.
    r.register(Lane("study001_nrr_audit", "science", True, andersen2019_rubric,
                    gen_nrr_papers,
                    "ORACLE: Andersen 2019 contamination rubric (PRESENCE FLOOR). "
                    "Zero-cost."))
    # Study 002 — validated, oracle = held-out adversary, honest abort baked in
    r.register(Lane("study002_deception_probe", "science", True, held_out_adversary_oracle,
                    gen_deception_probes,
                    "ORACLE: held-out adversary; INCONCLUSIVE if not held out."))
    for lane in REFUSED_RIDDLES:
        r.register(lane)
    return r


# ============================================================ execution (unattended)
def run_all(reg: Registry, *, dry_run: bool = False) -> dict:
    """One unattended pass. Returns the run report; the CLI prints it.

    dry_run reports what WOULD dispatch — routing, eligibility, unmet
    prerequisites — without spending a single headless call. It is how you check
    the wiring on a machine that cannot run the oracles.
    """
    report = {"started": _stamp(), "dry_run": dry_run,
              "blind_precision": BLIND_PRECISION, "refused": [], "lanes": []}

    for lane in reg.refused():
        _log_refusal(lane)                        # visible, so declines are auditable
        report["refused"].append({"lane": lane.name, "reason": lane.note})

    for lane in reg.eligible():
        row = {"lane": lane.name, "kind": lane.kind, "unmet_prerequisites": lane.unmet(),
               "generated": 0, "accepted": 0, "rejected": 0,
               "oracle_unavailable": 0, "degraded": None, "queued": []}
        if dry_run:
            report["lanes"].append(row)
            continue
        try:
            candidates = lane.generate()
        except GenerationUnavailable as exc:
            row["degraded"] = f"generator unavailable: {exc}"
            report["lanes"].append(row)
            continue
        row["generated"] = len(candidates)
        for cand in candidates:
            judgement = lane.oracle(cand)
            if not judgement.oracle_ran:
                row["oracle_unavailable"] += 1    # never confusable with "found nothing"
            elif judgement.accepted:
                row["accepted"] += 1
                row["queued"].append(str(_enqueue_review(lane, cand, judgement)))
            else:
                row["rejected"] += 1
            # REFUTED / FAIL / INCONCLUSIVE never surface to a human
        report["lanes"].append(row)

    put_control(f"runs/{report['started']}.json", report)
    return report


# ============================================================ the drafter
# Proposes new riddles into the validation queue. It CANNOT register a lane —
# predicate-author separation at the meta level. The thing that proposes frontier
# problems does not get to certify that their floor is real. That is your afternoon.
RIDDLE_VALIDATION_FORM = """\
FLOOR-VALIDATION — required before this riddle becomes an unattended lane.
Four corners (each demonstrated somewhere in the literature?):
  [ ] corner 1 charted   [ ] corner 2 charted   [ ] corner 3   [ ] corner 4
Ceiling:
  [ ] the stated ceiling is a habit-with-citations, not a law (name who set it)
Floor (THE oracle test):
  [ ] the floor is a theorem / conservation law / epistemic wall  -> NO ORACLE, human-only
  [ ] OR the floor is engineerable and a checkable rubric exists   -> name the oracle: __________
Only a riddle with a named oracle becomes an eligible lane. The rest are archived
as real-but-human-only. Guessing here rebuilds the prime sieve.
"""


def draft_riddles(*, dry_run: bool = False) -> dict:
    """Weekly: propose riddles for human floor-validation. Never registers a lane."""
    if dry_run:
        return {"drafted": 0, "dry_run": True}
    try:
        candidates = run_claude_json(
            "Read recent literature in the target field. Propose candidate riddles "
            "in the four-corners/ceiling/floor format as a JSON list. For each, "
            "state what the floor WOULD be. Do NOT assert the floor is real — that "
            "is the human's call. Output candidates only.",
            model="opus", tools="Read,Grep,Bash,WebSearch")
    except GenerationUnavailable as exc:
        return {"drafted": 0, "degraded": str(exc)}

    written = []
    for cand in candidates:
        stamp = _stamp()
        written.append(str(put_control(f"riddle_drafts/{stamp}_riddle.json", {
            "candidate_riddle": cand,
            "validation_form": RIDDLE_VALIDATION_FORM,
            "drafted": stamp,
            "status": "AWAITING_HUMAN_FLOOR_VALIDATION",
        })))
    return {"drafted": len(written), "paths": written}


# ============================================================ seams / util
def _enqueue_review(lane: Lane, cand: dict, judgement: Judgement):
    stamp = _stamp()
    record = {
        "lane": lane.name, "kind": lane.kind,
        "verdict": judgement.verdict, "oracle_detail": judgement.detail,
        "oracle_note": lane.note,
        "blind_precision": BLIND_PRECISION,       # never claim measured yield
        "calibration_needed": CALIBRATION_EVENT if BLIND_PRECISION == "UNMEASURED" else None,
        "candidate": cand, "queued": stamp,
        "human_step": ("three-field re-audit" if lane.kind == "verification"
                       else "spot-check the oracle's PASS"),
        "checklist": (REAUDIT_CHECKLIST if lane.kind == "verification"
                      else "Confirm the oracle's PASS is real: read the paper's "
                           "controls section and check each present control is "
                           "quantified, not merely named."),
    }
    return put_control(f"human_queue/{stamp}_{lane.name}.json", record)


def _log_refusal(lane: Lane) -> None:
    put_control(f"refused_log/{lane.name}.json", {
        "lane": lane.name, "kind": lane.kind, "reason": lane.note,
        "eligible": False, "logged": _stamp()})


def _stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")


if __name__ == "__main__":
    # Two systemd timers on the compute host call the CLI, not this module:
    #   discovery-run.timer    -> `discovery run`     (hourly / nightly)
    #   discovery-draft.timer  -> `discovery draft`   (weekly)
    # Running this file directly shows the eligible-vs-refused lane split.
    import sys

    from cli import main

    sys.exit(main(sys.argv[1:] or ["status"]))
