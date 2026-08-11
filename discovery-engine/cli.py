#!/usr/bin/env python3
"""cli.py — the surface the timers and the human both use.

    discovery status                 what is wired, what is refused, what is missing
    discovery run [--dry-run]        one unattended pass  (discovery-run.timer)
    discovery draft [--dry-run]      propose riddles      (discovery-draft.timer)
    discovery queue                  read both review queues as text
    discovery gate-selftest --repo   the M1 five-case smoke test on a real target

`run` and `draft` are separate subcommands precisely so a timer can invoke one
without the other. `--dry-run` proves the wiring without spending a headless call.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys

import paths
import verifygate_adapter as vg
from discovery_engine import build_registry, draft_riddles, run_all


def cmd_status(_args) -> int:
    paths.ensure_dirs()
    reg = build_registry()
    print(f"state root (git-tracked) : {paths.state_root()}")
    print(f"drive dir  (bulk only)   : {paths.drive_dir()}")
    print(f"targets                  : {len(paths.load_targets())} in {paths.targets_file().name}")
    print(f"claude CLI               : {'found' if shutil.which('claude') else 'NOT FOUND'}")
    print(f"blind precision          : UNMEASURED until the Sequence blind run")

    missing = vg.preflight()
    print(f"\nverifygate oracle        : {'READY' if not missing else 'NOT RUNNABLE HERE'}")
    for m in missing:
        print(f"  - missing: {m}")

    print("\neligible lanes (validated AND oracle):")
    for lane in reg.eligible():
        unmet = lane.unmet()
        flag = "" if not unmet else f"   [prerequisites unmet: {len(unmet)}]"
        print(f"  {lane.name:<26} {lane.kind:<13} {lane.note}{flag}")

    print("\nrefused lanes (real, but human-only — never faked):")
    for lane in reg.refused():
        print(f"  {lane.name:<26} {lane.kind:<13} {lane.note}")
    return 0


def cmd_run(args) -> int:
    paths.ensure_dirs()
    report = run_all(build_registry(), dry_run=args.dry_run)
    _print_run(report)
    return 0


def cmd_draft(args) -> int:
    paths.ensure_dirs()
    print(json.dumps(draft_riddles(dry_run=args.dry_run), indent=2))
    return 0


def cmd_queue(_args) -> int:
    paths.ensure_dirs()
    review = sorted(paths.q_review().glob("*.json"))
    drafts = sorted(paths.q_drafts().glob("*.json"))
    print(f"human_queue — {len(review)} item(s) awaiting your acceptance decision")
    for f in review:
        rec = json.loads(f.read_text())
        cand = rec.get("candidate", {})
        print(f"  [{rec.get('lane', '?')}] {f.name}")
        print(f"      verdict={rec.get('verdict')}  step={rec.get('human_step')}")
        print(f"      {str(cand.get('hypothesis') or cand.get('title') or '')[:100]}")
    print(f"\nriddle_drafts — {len(drafts)} riddle(s) awaiting floor-validation")
    for f in drafts:
        rec = json.loads(f.read_text())
        riddle = rec.get("candidate_riddle", {})
        print(f"  {f.name}: {str(riddle.get('title') or riddle)[:100]}")
    refused = sorted(paths.q_refused().glob("*.json"))
    print(f"\nrefused_log — {len(refused)} lane(s) the engine declined to fake")
    for f in refused:
        print(f"  {json.loads(f.read_text()).get('lane')}")
    return 0


def cmd_gate_selftest(args) -> int:
    result = vg.selftest(args.repo)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def _print_run(report: dict) -> None:
    mode = "DRY RUN — nothing generated, nothing gated" if report["dry_run"] else "live run"
    print(f"run {report['started']}  ({mode})")
    print(f"blind precision: {report['blind_precision']}\n")
    print("refused (registered, never faked):")
    for row in report["refused"]:
        print(f"  {row['lane']:<26} {row['reason']}")
    print("\nlanes:")
    for row in report["lanes"]:
        print(f"  {row['lane']:<26} generated={row['generated']} "
              f"accepted={row['accepted']} rejected={row['rejected']} "
              f"oracle_unavailable={row['oracle_unavailable']}")
        if row["unmet_prerequisites"]:
            for m in row["unmet_prerequisites"]:
                print(f"      prerequisite missing: {m}")
        if row["degraded"]:
            print(f"      DEGRADED: {row['degraded']}")
        for q in row["queued"]:
            print(f"      queued -> {q}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="discovery",
                                     description="Discovery engine — lanes, oracles, queues.")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show wiring, lanes, and unmet prerequisites.")

    r = sub.add_parser("run", help="One unattended pass over the eligible lanes.")
    r.add_argument("--dry-run", action="store_true",
                   help="Report dispatch without spending a headless call.")

    d = sub.add_parser("draft", help="Propose riddles for human floor-validation.")
    d.add_argument("--dry-run", action="store_true")

    sub.add_parser("queue", help="Print human_queue + riddle_drafts + refused_log.")

    g = sub.add_parser("gate-selftest",
                       help="Run the M1 five-case gate self-proof on a target checkout.")
    g.add_argument("--repo", required=True, help="Path to a cloned Foundry target.")

    args = parser.parse_args(argv)
    handlers = {"status": cmd_status, "run": cmd_run, "draft": cmd_draft,
                "queue": cmd_queue, "gate-selftest": cmd_gate_selftest}
    if args.command is None:
        return cmd_status(args)
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
