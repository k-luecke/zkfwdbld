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

    args = parser.parse_args(argv)

    if args.command == "model":
        return _cmd_model(args)
    parser.error(f"unknown command {args.command}")
    return 2


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
