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

    args = parser.parse_args(argv)

    if args.command == "model":
        return _cmd_model(args)
    if args.command == "verify":
        return _cmd_verify(args)
    parser.error(f"unknown command {args.command}")
    return 2


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
