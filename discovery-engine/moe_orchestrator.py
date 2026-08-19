#!/usr/bin/env python3
"""moe_orchestrator.py — thin orchestration-MoE over the existing verification stack.

WHAT THIS IS:
    Router -> specialized expert surfacers (headless Claude Code, overnight) ->
    VerifyGate machine gate (predicate-author separation) -> candidate queue ->
    the three-field re-audit (the only human step that remains).

WHAT THIS IS NOT:
    A trained mixture-of-experts model. The "MoE" here is dispatch logic, not a
    sparse-gated network. If you find yourself training a router model, stop —
    that's the months-long build, and it's not what makes any finding real.

HONESTY INVARIANT:
    blind_precision is UNMEASURED until the blind Sequence run executes. Every
    queued record carries that word. Do not tune thresholds against a yield you
    have not measured.
"""

from __future__ import annotations

import dataclasses
import datetime
import pathlib

import paths
import verifygate_adapter as vg
from headless import GenerationUnavailable, run_claude_json

# Portfolio-wide status the pipeline must not lie about.
BLIND_PRECISION = "UNMEASURED"          # set only after the Sequence blind run
CALIBRATION_EVENT = "code-423n4/2025-10-sequence (nonce-replay/signature lane)"


# ---------------------------------------------------------------- experts
@dataclasses.dataclass(frozen=True)
class Expert:
    name: str
    model: str            # opus for hard surface, sonnet for mechanical passes
    system: str           # lane-specific surfacing prompt / config path
    tags: tuple[str, ...] # surface-tags this expert claims

EXPERTS: list[Expert] = [
    Expert("access_control", "opus",
           "prompts/access_control.md",
           ("modifier_asymmetry", "cross_chain", "bridge", "guard_bypass")),
    Expert("signature_replay", "opus",
           "prompts/sig_replay.md",
           ("nonce", "signature", "eip191", "session_sig")),
    Expert("formal_verify", "sonnet",
           "prompts/formal.md",
           ("bls12_381", "pairing", "proof_artifact")),
]


def route(surface_tags: list[str]) -> Expert | None:
    """Surface-tag -> expert. Thin on purpose. First lane that claims a tag wins."""
    for e in EXPERTS:
        if set(surface_tags) & set(e.tags):
            return e
    return None


# ------------------------------------------------------ headless surfacer
def surface(expert: Expert, target: str) -> dict:
    """Run one expert headless on one target, JSON out.

    The expert PROPOSES. It never certifies — see gate() for why. Raises
    GenerationUnavailable if the surfacer could not run at all, which the caller
    records as a degraded lane rather than as "found nothing".
    """
    target_dir = pathlib.Path(target).expanduser()
    run_id = f"{expert.name}/{_stamp()}"
    prompt = (
        f"Surface candidate findings in {target_dir} for the {expert.name} lane.\n"
        f"Output a JSON list of hypothesis objects and nothing else. Each object: "
        f'{{"id", "hypothesis", "host_function", "bug_class", "adversary", '
        f'"evidence"}}.\n'
        f"Do NOT claim any hypothesis is confirmed, and do not include a verdict "
        f"or confidence field — the gate decides that, and any such field is "
        f"discarded before gating."
    )
    hypotheses = run_claude_json(
        prompt,
        model=expert.model,
        tools="Read,Grep,Bash",                  # scope tightly
        add_dir=str(target_dir) if target_dir.is_dir() else None,
        cwd=str(target_dir) if target_dir.is_dir() else None,
        max_turns=40,
    )
    for h in hypotheses:
        h.setdefault("target_repo", str(target_dir))
        h["surfaced_by"] = expert.name
        h["surfacer_model"] = expert.model
    return {"run_id": run_id, "expert": expert.name, "target": str(target_dir),
            "hypotheses": hypotheses}


# ------------------------------------------------------------- the gate
def gate(hypothesis: dict) -> dict:
    """VerifyGate four-phase fork-executed PoC: baseline -> control -> attack -> recheck.

    PREDICATE-AUTHOR SEPARATION (the load-bearing rule):
        The expert's own opinion of its hypothesis is DISCARDED here. Only the
        fork-executed verdict counts. This is what keeps the loop from
        accumulating confident garbage.
    """
    candidate = dict(hypothesis)
    for vote in ("self_verdict", "confidence", "verdict", "certainty", "likelihood"):
        candidate.pop(vote, None)                # the generator does not get a vote
    result = vg.verify(candidate)
    return {**candidate,
            "gate_verdict": result.verdict,
            "gate_reason": result.reason,
            "gate_available": result.available,
            "gate_raw_verdict": result.raw_verdict,
            "gate_predicate": result.predicate,
            "gate_detail": result.detail}


# --------------------------------------------------- human acceptance gate
REAUDIT_CHECKLIST = """\
THREE-FIELD BIDIRECTIONAL RE-AUDIT — required before any merge.
Forward (does the finding hold?):
  [ ] host function correct
  [ ] bug class correct
  [ ] adversary actually exists (a real caller can reach the sink)
Reverse (did we miss a row?):
  [ ] reverse pass: no omitted finding on this target
This is the human step. The pipeline cannot perform it — that's by design.
"""


def enqueue_for_review(candidate: dict) -> pathlib.Path | None:
    """Only gate-CONFIRMED candidates reach the queue. Everything else dies here."""
    if candidate.get("gate_verdict") != vg.CONFIRMED:
        return None
    record = {
        "candidate": candidate,
        "blind_precision": BLIND_PRECISION,       # never claim measured yield
        "calibration_needed": CALIBRATION_EVENT if BLIND_PRECISION == "UNMEASURED" else None,
        "reaudit": REAUDIT_CHECKLIST,
        "queued": _stamp(),
    }
    name = f"{_stamp()}_{candidate.get('id', 'cand')}.json"
    return paths.put_control(f"human_queue/{name}", record)


# ------------------------------------------------------------- the loop
def run(targets_with_tags: dict[str, list[str]]) -> list[dict]:
    """Contract lane, standalone. Returns one row per target for the run report."""
    rows: list[dict] = []
    for target, tags in targets_with_tags.items():
        expert = route(tags)
        if expert is None:
            rows.append({"target": target, "routed": None, "reason": "no_expert_claims_tags"})
            continue
        try:
            result = surface(expert, target)
        except GenerationUnavailable as exc:
            rows.append({"target": target, "routed": expert.name,
                         "degraded": str(exc)})
            continue
        queued = [str(p) for h in result["hypotheses"]
                  if (p := enqueue_for_review(gate(h))) is not None]
        rows.append({"target": target, "routed": expert.name,
                     "surfaced": len(result["hypotheses"]), "queued": queued})
    return rows


def _stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
