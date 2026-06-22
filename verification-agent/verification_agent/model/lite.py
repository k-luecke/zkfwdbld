"""Regex-lite extractor — degraded fallback when Slither can't compile.

This is NOT a Solidity parser and makes no correctness claims. It exists so the
harness still emits a verification-surface list when forge/solc are missing
(common in constrained CI). Any model built from this path is labeled degraded
in ``tool_status`` so no downstream stage trusts it as ground truth.

State label: PARTIAL (intentionally approximate; Slither is the real path).
"""

from __future__ import annotations

import re
from pathlib import Path

from ..schema import ContractInfo, FunctionInfo, StorageSlot
from .surface import tag_surfaces

_CONTRACT_RE = re.compile(
    r"\b(contract|interface|library|abstract\s+contract)\s+(\w+)"
    r"(?:\s+is\s+([^{]+))?", re.MULTILINE)
_FUNC_RE = re.compile(
    r"\bfunction\s+(\w+)\s*\(([^)]*)\)\s*([^;{]*?)\{", re.DOTALL)
_VISIBILITY_RE = re.compile(r"\b(external|public|internal|private)\b")
_MUTABILITY_RE = re.compile(r"\b(view|pure|payable)\b")
_MODIFIER_TOKENS = re.compile(r"\b(\w+)\b")


def extract_lite(sol_files: list[Path]) -> tuple[
        list[ContractInfo], list[StorageSlot], list[FunctionInfo]]:
    contracts: list[ContractInfo] = []
    storage: list[StorageSlot] = []
    entry_points: list[FunctionInfo] = []

    for path in sol_files:
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        rel = str(path)
        for cm in _CONTRACT_RE.finditer(text):
            kw, cname, parents = cm.group(1), cm.group(2), cm.group(3)
            kind = "abstract" if kw.startswith("abstract") else kw
            inh = [p.strip().split("(")[0] for p in parents.split(",")] if parents else []
            contracts.append(ContractInfo(
                name=cname, kind=kind, inheritance=[i for i in inh if i],
                source_file=rel))

        for fm in _FUNC_RE.finditer(text):
            name = fm.group(1)
            attrs = fm.group(3) or ""
            vis_m = _VISIBILITY_RE.search(attrs)
            visibility = vis_m.group(1) if vis_m else "public"
            if visibility in ("internal", "private"):
                continue  # entry points only
            mut_m = _MUTABILITY_RE.search(attrs)
            mutability = mut_m.group(1) if mut_m else "nonpayable"
            modifiers = _guess_modifiers(attrs)
            line = text[:fm.start()].count("\n") + 1
            surfaces = tag_surfaces(
                function_name=name,
                callees=None,
                source_body=_balanced_body(text, fm.end() - 1),
                modifiers=modifiers,
            )
            entry_points.append(FunctionInfo(
                contract=_enclosing_contract(text, fm.start(), contracts),
                name=name,
                signature=f"{name}({_arg_types(fm.group(2))})",
                visibility=visibility,
                mutability=mutability,
                modifiers=modifiers,
                is_entry_point=True,
                surfaces=list(surfaces.keys()),
                surface_evidence=surfaces,
                source_file=rel,
                source_line=line,
            ))
    return contracts, storage, entry_points


def _guess_modifiers(attrs: str) -> list[str]:
    known = {"external", "public", "internal", "private", "view", "pure",
             "payable", "virtual", "override", "returns"}
    toks = []
    for m in _MODIFIER_TOKENS.finditer(attrs):
        t = m.group(1)
        if t not in known and not t.isdigit():
            toks.append(t)
    return toks


def _arg_types(args: str) -> str:
    if not args.strip():
        return ""
    types = []
    for a in args.split(","):
        a = a.strip()
        if a:
            types.append(a.split()[0])
    return ",".join(types)


def _balanced_body(text: str, open_brace: int, max_span: int = 8000) -> str:
    """Return the function body delimited by balanced braces.

    ``open_brace`` is the index of the function's opening ``{``. We scan forward
    matching braces so the body never spills into the next function (which would
    cause cross-function keyword bleed and false surface tags). Strings/comments
    are not parsed out — good enough for keyword scanning, and recall-biased.
    """
    if open_brace < 0 or open_brace >= len(text) or text[open_brace] != "{":
        return ""
    depth = 0
    end = min(len(text), open_brace + max_span)
    for i in range(open_brace, end):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace:i + 1]
    return text[open_brace:end]


def _enclosing_contract(text: str, pos: int, contracts: list[ContractInfo]) -> str:
    best = "?"
    best_at = -1
    for cm in _CONTRACT_RE.finditer(text):
        if cm.start() < pos and cm.start() > best_at:
            best_at = cm.start()
            best = cm.group(2)
    return best
