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

    fp = sub.add_parser(
        "findpath",
        help="Run path backends to find a concrete path toward the break "
             "predicate, then optionally confirm via the gate (M4).")
    fp.add_argument("--model", required=True, help="Path to an M0 target model JSON.")
    fp.add_argument("--k", type=int, default=5, help="KB priors per function.")
    fp.add_argument("--run-external", action="store_true",
                    help="Also invoke the medusa/halmos backends (slow; bounded).")
    fp.add_argument("--repo", default=None,
                    help="Cloned target dir (needed for external backends / gate).")
    fp.add_argument("--connect-gate", action="store_true",
                    help="Confirm the discovered gate-bound path through the M1 gate.")
    fp.add_argument("--external-timeout", type=int, default=90)
    fp.add_argument("--json", default=None, help="Write the coverage map JSON.")

    bt = sub.add_parser(
        "backtest",
        help="Blind backtest over settled contests; frozen three-tier scorecard (M6).")
    bt.add_argument("--examples-dir", default="examples",
                    help="Directory holding the per-contest M0 model JSONs.")
    bt.add_argument("--decent-repo", default=None,
                    help="Cloned 2024-01-decent dir (for the M-03 gate confirmation).")
    bt.add_argument("--json", default=None, help="Write the frozen scorecard JSON.")

    sy = sub.add_parser(
        "synthesize",
        help="Synthesize a verify scenario from a Seer lead and run it through "
             "the UNCHANGED gate (M4.5).")
    sy.add_argument("--entrypoint", default="",
                    help="The unguarded entrypoint the lead flagged.")
    sy.add_argument("--guard", default="",
                    help="The guard/modifier the unguarded path bypasses.")
    sy.add_argument("--workspace", default=None,
                    help="Foundry workspace dir (created + forge-std provisioned).")
    sy.add_argument("--demo", action="store_true",
                    help="Run the M-03 structural lead + a Centrifuge permit lead.")
    sy.add_argument("--deploygraph", default=None,
                    help="Path to an M0 model: derive a target's collaborator "
                         "deploy+wiring backbone (and print the autonomy ledger).")
    sy.add_argument("--target", default=None, help="Target contract for --deploygraph.")
    sy.add_argument("--json", default=None, help="Write the synthesis run JSON.")

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
    if args.command == "findpath":
        return _cmd_findpath(args)
    if args.command == "backtest":
        return _cmd_backtest(args)
    if args.command == "synthesize":
        return _cmd_synthesize(args)
    parser.error(f"unknown command {args.command}")
    return 2


def _cmd_deploygraph(args) -> int:
    import json as _json

    from .synthesize.deploygraph import DeployGraphSynthesizer

    if not args.target:
        print("--deploygraph requires --target <ContractName>")
        return 2
    model = _json.loads(Path(args.deploygraph).read_text())
    g = DeployGraphSynthesizer().synthesize(model, args.target)
    print(f"Verification-Agent — M4.5 deploy-graph synthesis (target={args.target})")
    print("MACHINE-DERIVED from the M0 model alone (target-agnostic). The semantic "
          "mile below is NOT model-derivable — named, not papered over.\n")
    print("--- collaborator deploys ---")
    for d in g.deploys:
        tag = f"[MOCK SLOT {d.iface}]" if d.is_mock_slot else "(concrete)"
        print(f"   {d.var:14s} <- {d.contract} {tag}")
    print("--- owner-gated wiring ---")
    for w in g.wiring:
        print(f"   target.{w.setter}(address({w.collaborator_var}))")
    print("--- rendered deploy+wiring backbone (state-assignment form) ---")
    print(g.render_seed(as_assignment=True))
    print("\n--- semantic mile (NOT derivable from the model) ---")
    for s in g.semantic_gaps:
        print(f"   - {s}")
    if args.json:
        Path(args.json).write_text(_json.dumps(g.to_dict(), indent=2))
        print(f"\ndeploy-graph -> {args.json}")
    return 0


def _cmd_synthesize(args) -> int:
    import json as _json
    import tempfile

    from .synthesize import ScenarioSynthesizer, SynthesisRunner

    if args.deploygraph:
        return _cmd_deploygraph(args)

    syn = ScenarioSynthesizer()
    if args.demo:
        leads = [
            {"attack_entrypoint": "receiveFromBridge",
             "guard_bypassed": "retrieveAndCollectFees"},
            {"attack_entrypoint": "requestRedeemWithPermit",
             "guard_bypassed": "withApproval"},
        ]
    elif args.entrypoint:
        leads = [{"attack_entrypoint": args.entrypoint,
                  "guard_bypassed": args.guard}]
    else:
        print("provide --entrypoint (and --guard) or --demo")
        return 2

    ws = Path(args.workspace) if args.workspace else Path(tempfile.mkdtemp(prefix="synth_ws_"))
    runner = SynthesisRunner(ws)
    runner.ensure_workspace()

    print("Verification-Agent — M4.5 scenario synthesis (run through the UNCHANGED gate)")
    print("discipline: synthesized scenarios get no fast path; the Control phase "
          "rejects a machine-rigged predicate exactly as it would a human's.\n")

    out = []
    for lead in leads:
        sc = syn.synthesize(lead)
        rec = sc.to_dict()
        ep = sc.lead_entrypoint
        print(f"[lead] {ep}  (bypasses {sc.lead_guard or '-'})")
        print(f"   mechanism={sc.mechanism}  executable={sc.executable}  "
              f"self_contained={sc.is_self_contained}")
        if sc.executable:
            results = runner.run(sc)
            rec["results"] = [r.to_dict() for r in results]
            for r in results:
                flag = "OK " if r.gate_correct else "!! "
                print(f"   [{flag}] {r.case.role:14s} -> {r.verdict.value:28s} "
                      f"(expected {r.expected.value})")
            print(f"   autonomy: {sc.autonomy}")
            print(f"   real-finding gap: {sc.gap}")
        else:
            print(f"   NOT EXECUTABLE — honest gap:")
            print(f"     {sc.gap}")
        print()
        out.append(rec)

    if args.json:
        Path(args.json).write_text(_json.dumps({"milestone": "M4.5", "scenarios": out}, indent=2))
        print(f"synthesis run -> {args.json}")
    return 0


def _cmd_backtest(args) -> int:
    import json as _json
    from .backtest import (ANSWER_KEYS, CONTESTS, BlindRunner, aggregate,
                           score_contest)

    examples = Path(args.examples_dir)
    runner = BlindRunner()

    print("Verification-Agent — M6 backtest (FROZEN three-tier taxonomy; blind run)")
    print("taxonomy pinned before run: Tier1=path+verdict, Tier2=+PoC-synthesis, "
          "Tier3=surfaced-not-caught. A found path without a gate verdict is NOT a catch.\n")

    # ---- BLIND RUN (no answer keys read) ----
    runs = []
    for c in CONTESTS:
        models = [str(examples / m) for m in c["models"]]
        if not all(Path(m).exists() for m in models):
            print(f"[skip] {c['id']}: model(s) missing {models}")
            continue
        repo = args.decent_repo if c["id"] == "2024-01-decent" else None
        run = runner.run(c["id"], models, repo_dir=repo, confirm_gate=bool(repo))
        run["blind"] = c["blind"]
        runs.append(run)
        cc = run["counts"]
        tag = "BLIND" if c["blind"] else "calibration"
        print(f"[{tag:11s}] {c['id']:18s} surfaced={cc['surfaced']:3d} "
              f"hypotheses={cc['hypotheses']:3d} paths={cc['paths_found']:2d} "
              f"gate_confirmed={cc['gate_confirmed']}")

    # ---- SCORE (answer keys opened now) ----
    print("\n--- opening answer keys and scoring against the frozen taxonomy ---")
    scored = [score_contest(r, ANSWER_KEYS[r["contest_id"]]) for r in runs]
    for s in scored:
        print(f"\n{s['contest_id']} ({'blind' if s['blind'] else 'calibration'}):")
        for f in s["findings"]:
            if not f["in_lane"]:
                continue
            mark = {"tier1_autonomous_path_and_verdict": "TIER-1 CATCH",
                    "tier2_fully_autonomous_with_poc_synthesis": "TIER-2",
                    "tier3_surfaced_not_caught": "tier-3 surfaced",
                    "missed": "MISSED"}[f["tier"]]
            lead = " +Seer-lead" if f["path_found"] else ""
            print(f"   {f['id']:4s} [{f['mechanism']:18s}] {mark}{lead}  — {f['title'][:54]}")

    agg = aggregate(scored)
    print("\n================ FROZEN SCORECARD (lane: access-control / cross-chain) ================")
    print(f"in-lane findings across {len(scored)} contest(s): {agg['in_lane_findings']}")
    print(f"  TIER-1 autonomous path + verdict : {agg['tier1_autonomous_path_and_verdict']['count']} "
          f"(recall {agg['tier1_autonomous_path_and_verdict']['recall']})  "
          f"ids={agg['tier1_autonomous_path_and_verdict']['ids']}")
    print(f"  TIER-2 fully autonomous (PoC syn): {agg['tier2_fully_autonomous']['count']} "
          f"(recall {agg['tier2_fully_autonomous']['recall']})  [near-zero until M4.5]")
    print(f"  TIER-3 surfaced not caught       : {agg['tier3_surfaced_not_caught']['count']}")
    print(f"  surfaced total (tier-3 and up)   : {agg['surfaced_total']['count']} "
          f"(recall {agg['surfaced_total']['recall']})")
    print(f"  Seer path-leads on findings      : {agg['path_found_leads_on_findings']['count']} "
          f"(NOT catches — leads only)")

    if args.json:
        payload = {"taxonomy": "frozen", "runs": runs, "scored": scored, "aggregate": agg}
        Path(args.json).write_text(_json.dumps(payload, indent=2))
        print(f"\nfrozen scorecard -> {args.json}")
    return 0


def _cmd_findpath(args) -> int:
    import json as _json
    from .hypothesize import HypothesisEngine
    from .pathfind import PathOrchestrator

    model = _json.loads(Path(args.model).read_text())
    hyps = HypothesisEngine(k_priors=args.k).run(model)
    orch = PathOrchestrator()
    report = orch.run(hyps, model, repo_dir=args.repo,
                      run_external=args.run_external,
                      external_timeout=args.external_timeout)

    print("Verification-Agent — M4 path backends (search toward the break predicate)")
    print(f"backends: " + ", ".join(
        f"{b['name']}({'available' if b['available'] else 'unavailable'})"
        for b in report["backends"]))

    found = [r for r in report["results"] if r["found"]]
    print(f"\nfound {len(found)} concrete path(s):")
    seen = set()
    for r in found:
        key = (r["backend"], r["attack_entrypoint"], r["guard_bypassed"])
        if key in seen:
            continue
        seen.add(key)
        print(f"  [{r['backend']}] attack entrypoint: {r['attack_entrypoint']}  "
              f"reaches {r['reaches']}  bypasses [{r['guard_bypassed']}]"
              f"{'  [gate-bound]' if r['gate_binding'] else ''}")
        print(f"      {r['notes']}")

    print(f"\ncoverage map (per-backend status counts):")
    for b, counts in report["coverage"]["by_backend"].items():
        print(f"  {b:16s} {counts}")
    print(f"by mechanism: {report['coverage']['by_mechanism']}")

    if args.connect_gate and args.repo:
        _findpath_connect_gate(found, args.repo)

    if args.json:
        Path(args.json).write_text(_json.dumps(report, indent=2))
        print(f"\ncoverage map -> {args.json}")
    return 0


def _findpath_connect_gate(found_paths, repo) -> None:
    """Machine-found path -> machine verdict: confirm the discovered gate-bound
    path through the M1 gate. The handoff lives here in the orchestrator layer,
    not inside pathfind/ (which never imports the gate)."""
    from .verify import DECENT_M1_CASES, VerifyHarness

    bound = next((r for r in found_paths if r.get("gate_binding")), None)
    if not bound:
        print("\n[connect-gate] no gate-bound discovered path.")
        return
    binding = bound["gate_binding"]
    case = next((c for c in DECENT_M1_CASES if c.contract_name == binding), None)
    if not case:
        print(f"\n[connect-gate] no M1 case for binding {binding}.")
        return
    print(f"\n[connect-gate] {bound['backend']} found the path "
          f"'{bound['attack_entrypoint']}' (bypassing {bound['guard_bypassed']}); "
          f"handing it to the M1 gate ({binding}) ...")
    r = VerifyHarness(Path(repo)).run_suite([case])[0]
    print(f"  gate verdict: {r.verdict.value}")
    print("  -> path was MACHINE-FOUND (Seer, from the model) and "
          "MACHINE-VERIFIED (gate, by execution). No hand-written attack in the "
          "discovery step.")


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
