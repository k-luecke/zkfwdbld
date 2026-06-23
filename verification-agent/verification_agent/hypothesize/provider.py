"""Hypothesis providers — offline (default) and Claude (pluggable).

The provider turns (a priority function + its KB priors) into candidate
hypotheses. The OFFLINE provider is a real, deterministic generator grounded in
the KB priors and the invariant library — it makes the whole loop runnable with
no network. The CLAUDE provider is the stronger generator that drops in when the
Anthropic API is reachable; it produces the same `Hypothesis` schema.

Neither provider imports the verify gate. The LLM's confidence is advisory and
carries zero weight on any verdict (see schema.py).

State label: IMPLEMENTED (offline). Claude provider: PARTIAL (wired, untested
here — no API key / network).
"""

from __future__ import annotations

from typing import Any, Protocol

from . import ev as _ev
from .invariants import invariant_for
from .schema import Hypothesis


class HypothesisProvider(Protocol):
    def propose(self, function: dict[str, Any], priors: list) -> list[Hypothesis]: ...


def _evidence_terms(function: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for ev_list in (function.get("surface_evidence") or {}).values():
        terms.extend(ev_list)
    return terms


class OfflineHypothesisProvider:
    """Deterministic, KB-grounded generator. No network."""

    def __init__(self, max_per_function: int = 1):
        self.max_per_function = max_per_function

    def propose(self, function: dict[str, Any], priors: list) -> list[Hypothesis]:
        if not priors:
            return []
        contract = function.get("contract", "?")
        fn = function.get("name", "?")
        surfaces = list(function.get("surfaces", []))
        evidence = _evidence_terms(function)

        out: list[Hypothesis] = []
        for i, prior in enumerate(priors[: self.max_per_function]):
            e = prior.entry
            inv = invariant_for(
                root_cause=e.root_cause_category,
                bug_class=e.bug_class,
                invariant_violated=e.invariant_violated,
                target_contract=contract,
                target_function=fn,
            )
            sketch = [
                f"Reach {contract}.{fn} as an unprivileged caller.",
                f"Drive the privileged effect via the shape: {e.entrypoint_shape}.",
                f"Observe the break: {inv.break_expectation}",
            ]
            ev_score = _ev.score_ev(
                root_cause=e.root_cause_category,
                prior_strength=prior.score,
                surfaces=surfaces,
                evidence_terms=evidence,
                attack_steps=len(sketch),
            )
            out.append(Hypothesis(
                id=f"hyp::{contract}.{fn}::{e.bug_class}::{i}",
                target_contract=contract,
                target_function=fn,
                surfaces=surfaces,
                bug_class=e.bug_class,
                root_cause=e.root_cause_category,
                invariant_violated=e.invariant_violated,
                invariant=inv,
                attack_sketch=sketch,
                ev=ev_score,
                prior_ids=[e.id],
                prior_sources=[e.source.value],
                statement=(
                    f"A call sequence reaching {contract}.{fn} may reach a state "
                    f"violating '{inv.name}', root-cause class '{e.bug_class}' "
                    f"(grounded on {e.id})."),
                # Advisory only — explicitly the KB match strength, not a verdict.
                llm_confidence=round(prior.score, 4),
                generator="offline",
            ))
        return out


# ---------------------------------------------------------------------------
# Claude provider — wired per the current Anthropic SDK (model claude-opus-4-8,
# adaptive thinking, strict tool schema for structured output). Not exercised in
# this environment (no API key / blocked network); the offline provider is the
# default. See docs/M3_hypothesis_engine.md.
# ---------------------------------------------------------------------------

_HYPOTHESIS_TOOL = {
    "name": "emit_hypotheses",
    "description": "Emit candidate vulnerability hypotheses for the gate to verify.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "hypotheses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "statement": {"type": "string"},
                        "bug_class": {"type": "string"},
                        "root_cause": {"type": "string"},
                        "invariant_violated": {"type": "string"},
                        "invariant_description": {"type": "string"},
                        "baseline_expectation": {"type": "string"},
                        "control_expectation": {"type": "string"},
                        "break_expectation": {"type": "string"},
                        "attack_sketch": {"type": "array", "items": {"type": "string"}},
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "statement", "bug_class", "root_cause", "invariant_violated",
                        "invariant_description", "baseline_expectation",
                        "control_expectation", "break_expectation", "attack_sketch",
                        "confidence",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["hypotheses"],
        "additionalProperties": False,
    },
}


class ClaudeHypothesisProvider:
    """LLM generator grounded on KB priors + the invariant library.

    The LLM only *aims* the gate at good targets and drafts the predicate; it
    never vouches for what it aims at. Its confidence is recorded as advisory
    metadata and dropped before any verdict.
    """

    MODEL = "claude-opus-4-8"

    def __init__(self, client: Any | None = None):
        # Lazily construct the SDK client so importing this module never requires
        # the anthropic package or an API key.
        self._client = client

    def _ensure_client(self):
        if self._client is None:
            import anthropic  # imported lazily
            self._client = anthropic.Anthropic()
        return self._client

    def propose(self, function: dict[str, Any], priors: list) -> list[Hypothesis]:
        client = self._ensure_client()
        contract = function.get("contract", "?")
        fn = function.get("name", "?")
        surfaces = list(function.get("surfaces", []))
        prior_blurbs = "\n".join(
            f"- [{p.entry.source.value}] {p.entry.bug_class}: {p.entry.mechanism}"
            for p in priors[:5])
        system = (
            "You are a smart-contract vulnerability hypothesizer specialized in "
            "verification, reachability, and cross-chain/ZK bugs. You PROPOSE "
            "hypotheses for an execution gate to verify; you never assert a "
            "finding. The most important field is the invariant predicate: it "
            "must hold on honest state, survive a legitimate action, and be "
            "specifically broken by the attack. Ground each hypothesis in the "
            "provided prior mechanisms.")
        user = (
            f"Target: {contract}.{fn}\nSurfaces: {', '.join(surfaces)}\n"
            f"Function signature: {function.get('signature','')}\n"
            f"Evidence: {function.get('surface_evidence', {})}\n\n"
            f"Candidate mechanisms (priors from the knowledge base):\n{prior_blurbs}\n\n"
            "Emit 1-2 hypotheses via the emit_hypotheses tool. Make the invariant "
            "mechanism-specific and gate-survivable.")
        msg = client.messages.create(
            model=self.MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            tools=[_HYPOTHESIS_TOOL],
            tool_choice={"type": "tool", "name": "emit_hypotheses"},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return self._parse(msg, function, priors)

    def _parse(self, msg, function, priors) -> list[Hypothesis]:
        contract = function.get("contract", "?")
        fn = function.get("name", "?")
        surfaces = list(function.get("surfaces", []))
        evidence = _evidence_terms(function)
        prior_ids = [p.entry.id for p in priors[:5]]
        prior_sources = [p.entry.source.value for p in priors[:5]]
        top_prior_score = priors[0].score if priors else 0.0

        from .schema import InvariantSpec
        out: list[Hypothesis] = []
        for blk in getattr(msg, "content", []):
            if getattr(blk, "type", None) != "tool_use":
                continue
            for j, h in enumerate(blk.input.get("hypotheses", [])):
                inv = InvariantSpec(
                    name=h["invariant_violated"] or "invariant",
                    predicate_kind="llm",
                    description=h["invariant_description"],
                    baseline_expectation=h["baseline_expectation"],
                    control_expectation=h["control_expectation"],
                    break_expectation=h["break_expectation"],
                )
                ev_score = _ev.score_ev(
                    root_cause=h["root_cause"],
                    prior_strength=top_prior_score,
                    surfaces=surfaces,
                    evidence_terms=evidence,
                    attack_steps=len(h["attack_sketch"]) or 1,
                )
                out.append(Hypothesis(
                    id=f"hyp::{contract}.{fn}::claude::{j}",
                    target_contract=contract, target_function=fn,
                    surfaces=surfaces, bug_class=h["bug_class"],
                    root_cause=h["root_cause"],
                    invariant_violated=h["invariant_violated"],
                    invariant=inv, attack_sketch=h["attack_sketch"],
                    ev=ev_score, prior_ids=prior_ids, prior_sources=prior_sources,
                    statement=h["statement"],
                    llm_confidence=float(h.get("confidence", 0.0)),  # advisory only
                    generator="claude"))
        return out
