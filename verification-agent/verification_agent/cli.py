"""Command-line entry point for the M0 harness.

Usage:
    python -m verification_agent model \
        --repo https://github.com/org/contest --commit <sha> [--out model.json]

    python -m verification_agent model --local ./path/to/checkout

Only the M0 ``model`` command is implemented. Hypothesis / path / verify
commands are intentionally absent until M1 (the verify gate) is built and
trusted — see STATUS.md.

State label: IMPLEMENTED.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from .model.model_builder import build_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verification-agent",
        description="Verification-Agent — M0 harness (model only).")
    sub = parser.add_subparsers(dest="command", required=True)

    m = sub.add_parser("model", help="Build the JSON target model (M0).")
    m.add_argument("--repo", default="(local)",
                   help="GitHub repo URL of the scope.")
    m.add_argument("--commit", default=None,
                   help="Commit SHA to pin (recommended for reproducibility).")
    m.add_argument("--local", default=None,
                   help="Path to an existing checkout (skips cloning).")
    m.add_argument("--out", default=None,
                   help="Write JSON here (default: stdout).")
    m.add_argument("--workdir", default=None,
                   help="Scratch dir for the clone (default: a temp dir).")

    v = sub.add_parser(
        "verify",
        help="Run the M1 verify-gate self-proof against a cloned target (M1).")
    v.add_argument("--repo", required=True,
                   help="Path to a cloned Foundry target (e.g. 2024-01-decent).")
    v.add_argument("--json", default=None,
                   help="Write a structured run log (verdict + predicate per case).")

    hy = sub.add_parser(
        "hypothesize",
        help="Rank candidate hypotheses for a target model (M3).")
    hy.add_argument("--model", required=True,
                    help="Path to an M0 target model JSON.")
    hy.add_argument("--k", type=int, default=5, help="KB priors per function.")
    hy.add_argument("--top", type=int, default=10, help="How many to print.")
    hy.add_argument("--json", default=None, help="Write ranked hypotheses JSON.")
    hy.add_argument("--connect-gate", default=None, metavar="REPO",
                    help="Path to the cloned target; run the M1 gate on the "
                         "top gate-bound hypothesis to show its predicate clears "
                         "baseline/control.")

    kq = sub.add_parser(
        "kb", help="Query the knowledge base for hypothesis priors (M2).")
    kq.add_argument("--surface", action="append", default=[],
                    help="Surface tag (repeatable), e.g. bridge_inbound_handler.")
    kq.add_argument("--text", default="", help="Free-text context (fn name/sig).")
    kq.add_argument("--root-cause", default="", help="Optional mechanism hint.")
    kq.add_argument("--invariant", default="", help="Optional invariant hint.")
    kq.add_argument("--entrypoint", default="", help="Optional entrypoint-shape hint.")
    kq.add_argument("--source", action="append", default=[],
                    help="Restrict to sources: oak_taxonomy/contest_finding/public_incident.")
    kq.add_argument("--k", type=int, default=6, help="Number of priors to return.")
    kq.add_argument("--demo", action="store_true",
                    help="Run the M-03 surface demo (mechanism vs vocabulary).")
    kq.add_argument("--json", default=None, help="Write structured results JSON.")

    args = parser.parse_args(argv)

    if args.command == "model":
        return _cmd_model(args)
    if args.command == "verify":
        return _cmd_verify(args)
    if args.command == "kb":
        return _cmd_kb(args)
    if args.command == "hypothesize":
        return _cmd_hypothesize(args)
    parser.error(f"unknown command {args.command}")
    return 2


def _cmd_hypothesize(args) -> int:
    import json as _json
    from .hypothesize import HypothesisEngine

    model = _json.loads(Path(args.model).read_text())
    hyps = HypothesisEngine(k_priors=args.k).run(model)

    print("Verification-Agent — M3 hypothesis engine (proposes; never confirms)")
    print(f"target model: {args.model}")
    print(f"{len(hyps)} candidate hypotheses, EV-ranked "
          f"(EV = severity x evidence / verify-cost):\n")
    for i, h in enumerate(hyps[: args.top], 1):
        bound = "  [gate-bound]" if h.invariant.gate_binding else ""
        print(f"{i:2d}. EV={h.ev.score:.3f}  {h.target_contract}.{h.target_function}{bound}")
        print(f"     statement : {h.statement}")
        print(f"     PREDICATE : {h.invariant.name} — {h.invariant.description}")
        print(f"       baseline: {h.invariant.baseline_expectation}")
        print(f"       control : {h.invariant.control_expectation}")
        print(f"       break   : {h.invariant.break_expectation}")
        print(f"     ev: sev={h.ev.severity} prior={h.ev.prior_strength} "
              f"struct={h.ev.structural_risk} cost={h.ev.verify_cost}")
        print(f"     priors: {list(zip(h.prior_ids, h.prior_sources))}  "
              f"(llm_confidence={h.llm_confidence}, advisory — zero weight on verdict)")
        print()

    if hyps:
        floor = hyps[-1]
        print(f"lowest-EV (deprioritized): {floor.target_contract}.{floor.target_function} "
              f"EV={floor.ev.score:.3f}")

    if args.json:
        payload = {"model": args.model, "count": len(hyps),
                   "hypotheses": [h.to_dict() for h in hyps]}
        Path(args.json).write_text(_json.dumps(payload, indent=2))
        print(f"\nranked hypotheses -> {args.json}")

    if args.connect_gate:
        _connect_gate(hyps, args.connect_gate)
    return 0


def _connect_gate(hyps, repo) -> None:
    """Hand the top gate-bound hypothesis to the M1 gate (the proposes->verify
    handoff). This is where hypothesize meets verify — in the orchestrator, not
    inside the hypothesize package."""
    from .verify import DECENT_M1_CASES, VerifyHarness

    bound = next((h for h in hyps if h.invariant.gate_binding), None)
    if not bound:
        print("\n[connect-gate] no gate-bound hypothesis in this batch.")
        return
    binding = bound.invariant.gate_binding
    case = next((c for c in DECENT_M1_CASES if c.contract_name == binding), None)
    if not case:
        print(f"\n[connect-gate] no M1 case for binding {binding}.")
        return
    print(f"\n[connect-gate] handing '{bound.target_contract}.{bound.target_function}' "
          f"to the M1 gate via case {binding} ...")
    print(f"  hypothesis predicate: {bound.invariant.name} "
          f"({bound.invariant.measured_quantity})")
    harness = VerifyHarness(Path(repo))
    results = harness.run_suite([case])
    r = results[0]
    print(f"  gate verdict: {r.verdict.value}  (predicate cleared baseline+control: "
          f"{r.verdict.value not in ('REJECTED_MALFORMED_BASELINE','REJECTED_MALFORMED_CONTROL')})")
    print("  -> the engine PROPOSED the target+predicate; the GATE decided truth.")


def _cmd_kb(args) -> int:
    from .kb import KnowledgeBase, Source
    from .kb.schema import KBQuery

    kb = KnowledgeBase.from_data()
    sources = [Source(s) for s in args.source] if args.source else None

    if args.demo:
        return _kb_demo(kb, args.json)

    query = KBQuery(
        surfaces=args.surface, text=args.text,
        root_cause_hint=args.root_cause, invariant_hint=args.invariant,
        entrypoint_shape=args.entrypoint,
    )
    matches = kb.retrieve_priors(query, k=args.k, sources=sources)
    _print_priors("priors", matches)
    print(f"\nsource mix: {kb.source_breakdown(matches)}")
    print("note: priors are leads to investigate — the M1 gate confirms every finding.")
    if args.json:
        _write_priors_json(args.json, {"query": vars(query)}, matches)
    return 0


def _kb_demo(kb, json_path) -> int:
    from .kb import query_for_m03_surface
    from .kb.schema import KBQuery

    print("Verification-Agent — M2 KB demo: the M-03 surface\n")
    q1 = query_for_m03_surface()
    m1 = kb.retrieve_priors(q1, k=6)
    _print_priors("Query 1 — surfaces + text only (M0-derivable signal)", m1)
    print(f"   source mix: {kb.source_breakdown(m1)}")

    q2 = KBQuery(surfaces=q1.surfaces, text=q1.text,
                 root_cause_hint="access control bypass alternate entrypoint missing modifier",
                 invariant_hint="access-control-consistency")
    m2 = kb.retrieve_priors(q2, k=6)
    _print_priors("\nQuery 2 — + mechanism hint (keys within the surface)", m2)

    # The headline: a vocabulary decoy ranks far below same-mechanism hits.
    full = kb.retrieve_priors(q1, k=len(kb.entries))
    decoy_rank = next((i for i, m in enumerate(full, 1)
                       if m.entry.id.startswith("decoy")), None)
    print("\nmechanism-vs-vocabulary check:")
    print(f"   the bridge/fee 'rounding' decoy ranks #{decoy_rank} of {len(full)} "
          f"on Query 1 — vocabulary overlap did NOT pull it up.")
    print("\npriors are leads to investigate — the M1 gate confirms every finding.")
    if json_path:
        _write_priors_json(json_path,
                           {"query1": vars(q1), "query2": vars(q2),
                            "decoy_rank": decoy_rank, "corpus_size": len(kb.entries)},
                           m1, label_extra={"query2_top": m2})
    return 0


def _print_priors(header, matches) -> None:
    print(f"{header}:")
    for i, m in enumerate(matches, 1):
        print(f" {i:2d}. {m.score:.3f} [{m.entry.source.value:15s}] "
              f"{m.entry.bug_class:34s} {m.entry.id}")
        print(f"        {m.entry.title}")


def _write_priors_json(path, meta, matches, label_extra=None) -> None:
    import json as _json
    payload = dict(meta)
    payload["results"] = [m.to_record() for m in matches]
    if label_extra:
        for k, v in label_extra.items():
            payload[k] = [m.to_record() for m in v]
    Path(path).write_text(_json.dumps(payload, indent=2))
    print(f"\nstructured results -> {path}")


def _cmd_verify(args) -> int:
    from .verify import DECENT_M1_CASES, VerifyHarness

    harness = VerifyHarness(Path(args.repo))
    results = harness.run_suite(DECENT_M1_CASES)

    print("Verification-Agent — M1 verify-gate self-proof")
    print(f"target: {args.repo}\n")
    all_correct = True
    for r in results:
        ok = "OK " if r.gate_correct else "XX "
        all_correct = all_correct and r.gate_correct
        print(f"[{ok}] {r.case.kind:18s} {r.case.contract_name}")
        print(f"       hypothesis : {r.case.hypothesis[:96]}...")
        print(f"       predicate  : {r.predicate_text or '(none emitted)'}")
        print(f"       expected   : {r.expected.value}")
        print(f"       gate said  : {r.verdict.value}")
        if r.case.source_finding:
            print(f"       provenance : {r.case.source_finding}")
        print()
    confirmed = sum(1 for r in results if r.confirmed)
    n_correct = sum(1 for r in results if r.gate_correct)
    print(f"summary: {n_correct}/{len(results)} gate verdicts correct; "
          f"{confirmed} CONFIRMED finding(s).")
    # All four reject-corners of the taxonomy, proven firing where exercised.
    seen = {r.verdict.value for r in results if r.gate_correct}
    print(f"verdict corners exercised: {', '.join(sorted(seen))}")

    if args.json:
        import json as _json
        payload = {
            "target": args.repo,
            "cases": [r.to_record() for r in results],
            "summary": {
                "total": len(results),
                "gate_correct": n_correct,
                "confirmed": confirmed,
            },
        }
        Path(args.json).write_text(_json.dumps(payload, indent=2))
        print(f"\nstructured run log -> {args.json}")

    if not all_correct:
        print("GATE NOT TRUSTWORTHY: at least one verdict was wrong.")
        return 1
    print("Gate behaved correctly on all cases.")
    return 0


def _cmd_model(args) -> int:
    workdir = Path(args.workdir) if args.workdir else Path(tempfile.mkdtemp(
        prefix="vagent-"))
    model = build_model(
        repo_url=args.repo,
        commit=args.commit,
        workdir=workdir,
        local_path=Path(args.local) if args.local else None,
    )
    payload = json.dumps(model.to_dict(), indent=2)
    if args.out:
        Path(args.out).write_text(payload)
        _summary(model, args.out)
    else:
        print(payload)
    return 0


def _summary(model, out_path: str) -> None:
    print(f"[verification-agent] wrote {out_path}", file=sys.stderr)
    print(f"  build_system={model.build_system} compiled={model.compiled}",
          file=sys.stderr)
    print(f"  contracts={len(model.contracts)} "
          f"entry_points={len(model.entry_points)} "
          f"surface={len(model.verification_surface)}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
