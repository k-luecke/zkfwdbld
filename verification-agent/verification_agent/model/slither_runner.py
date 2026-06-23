"""Slither front-end — extract the structural model.

We do not parse Solidity. Slither (via crytic-compile) gives us the call graph,
entry points, inheritance linearization, storage variables, and external-call
edges. This module turns Slither's object model into our ``TargetModel`` pieces.

If Slither is unavailable or fails to compile the target, the caller falls back
to the regex-lite extractor so M0 still emits a (clearly degraded) model.

State label: IMPLEMENTED.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..schema import (
    CallEdge,
    ContractInfo,
    FunctionInfo,
    StorageSlot,
)
from .surface import tag_structural, tag_surfaces


@dataclass
class SlitherExtract:
    contracts: list[ContractInfo]
    storage_layout: list[StorageSlot]
    entry_points: list[FunctionInfo]
    call_graph: list[CallEdge]
    version: str | None


def slither_available() -> bool:
    try:
        import slither  # noqa: F401
        return True
    except Exception:
        return False


def _ensure_foundry_build_info(target: Path) -> bool:
    """Generate Foundry `out/build-info` so Slither can consume it offline.

    crytic-compile's foundry platform re-runs `forge build` without `--build-info`,
    which fails on projects that need it ("out/build-info is not a directory").
    We generate it explicitly in the foundry root and let Slither ignore compile.
    General M0 robustness — not target-specific.
    """
    import os
    import subprocess

    root = target if (target / "foundry.toml").exists() else None
    if root is None:
        for child in sorted(p for p in target.iterdir() if p.is_dir()) if target.is_dir() else []:
            if (child / "foundry.toml").exists():
                root = child
                break
    if root is None:
        return False
    env = dict(os.environ)
    foundry_bin = Path.home() / ".foundry" / "bin"
    if foundry_bin.is_dir():
        env["PATH"] = f"{foundry_bin}{os.pathsep}{env.get('PATH', '')}"
    env.setdefault("FOUNDRY_OFFLINE", "true")
    svm = Path.home() / ".svm"
    if svm.is_dir():
        env.setdefault("SVM_HOME", str(svm))
    try:
        subprocess.run(["forge", "build", "--build-info"], cwd=str(root),
                       env=env, capture_output=True, text=True, timeout=400)
    except Exception:
        return False
    return any(root.glob("**/build-info/*.json"))


def run_slither(target: Path) -> SlitherExtract:
    """Run Slither over ``target`` (a project dir or a single .sol file)."""
    from slither import Slither  # imported lazily so the package loads without it

    try:
        sl = Slither(str(target))
    except Exception:
        # Foundry build-info may be missing; generate it and retry ignoring compile.
        if _ensure_foundry_build_info(target):
            sl = Slither(str(target), ignore_compile=True)
        else:
            raise

    contracts: list[ContractInfo] = []
    storage: list[StorageSlot] = []
    entry_points: list[FunctionInfo] = []
    edges: list[CallEdge] = []

    for contract in sl.contracts:
        # Skip test/script/mock contracts and pulled-in dependencies; the
        # verification surface lives in the protocol's own code.
        if _is_noise(contract):
            continue

        kind = (
            "interface" if contract.is_interface
            else "library" if contract.is_library
            else "abstract" if contract.is_abstract
            else "contract"
        )
        contracts.append(ContractInfo(
            name=contract.name,
            kind=kind,
            inheritance=[c.name for c in contract.inheritance],
            source_file=_src_file(contract),
        ))

        # Interfaces declare functions but implement nothing — they are not
        # attacker-reachable entry points. Keep them in the contract list (for
        # the call graph) but don't model their declarations as the surface.
        if contract.is_interface:
            continue

        # Storage layout: declared, mutable state variables in declaration
        # order. Exact packed slots require `forge inspect`; we record order
        # and leave slot/offset null rather than guess (honest labeling).
        for sv in contract.state_variables_ordered:
            if sv.is_constant or sv.is_immutable:
                continue
            if sv.contract != contract:
                continue  # avoid double-listing inherited vars
            storage.append(StorageSlot(
                contract=contract.name,
                name=sv.name,
                type=str(sv.type),
            ))

        for func in contract.functions_entry_points:
            if getattr(func, "is_constructor", False):
                continue  # runs once at deploy; not an attacker-reachable entry
            # Skip functions an in-scope contract merely INHERITS from a
            # dependency (ERC20/OFT/LzApp boilerplate). We model the protocol's
            # own code, identified by where the function is actually defined.
            if _is_dependency_path(_func_def_file(func)):
                continue
            full = func.full_name  # name(arg types)
            callees, ext_edges = _calls(func)
            for callee, is_ext in ext_edges:
                edges.append(CallEdge(
                    caller=f"{contract.name}.{func.name}",
                    callee=callee,
                    external=is_ext,
                ))
            mod_names = [m.name for m in func.modifiers]
            keyword_surfaces = tag_surfaces(
                function_name=func.name,
                callees=callees,
                source_body=_func_source(func),
                modifiers=mod_names,
            )
            # Structural (name-independent) signal — the recall fix. Uses
            # transitive facts so a delegating entrypoint (e.g. receiveFromBridge
            # -> _swapAndExecute -> executor.execute) is caught.
            writes_state, makes_ext = _behavioral_facts(func)
            structural = tag_structural(
                is_entry_point=True,
                writes_state=writes_state,
                makes_external_calls=makes_ext,
                modifiers=mod_names,
                is_state_mutating=_mutability(func) not in ("view", "pure"),
            )
            surfaces = {**keyword_surfaces, **structural}
            has_structural = bool(structural)
            has_keyword = bool(keyword_surfaces)
            fi = FunctionInfo(
                contract=contract.name,
                name=func.name,
                signature=full,
                visibility=func.visibility,
                mutability=_mutability(func),
                modifiers=mod_names,
                is_entry_point=True,
                surfaces=list(surfaces.keys()),
                surface_evidence=surfaces,
                structural_priority=has_structural,
                confidence=_confidence(has_structural, has_keyword),
                source_file=_src_file(contract),
                source_line=_func_line(func),
            )
            entry_points.append(fi)

    return SlitherExtract(contracts, storage, entry_points, edges, _slither_version())


def _slither_version() -> str | None:
    try:
        from importlib.metadata import version
        return version("slither-analyzer")
    except Exception:
        return None


def _is_noise(contract) -> bool:
    """Filter test/script/mock code and well-known dependency libraries.

    We intentionally do NOT filter every ``lib/`` path: contests often vendor
    their own protocol code as a lib (e.g. ``lib/decent-bridge``), which IS in
    scope. We only drop named third-party dependencies.
    """
    name = contract.name.lower()
    if _is_dependency_path(_src_file(contract)):
        return True
    if name.endswith("test") or name.endswith("mock") or name.startswith("mock"):
        return True
    return False


_NOISY_PATHS = ("/test/", "/tests/", "/script/", "/mock", "/node_modules/")
_DEPENDENCY_LIBS = (
    "/forge-std/", "/openzeppelin-contracts", "/openzeppelin/", "/solmate/",
    "/solady/", "/ds-test/", "/permit2/", "/prb-math/", "/erc4626-tests/",
    "/createx/", "/layerzero", "/lz-evm", "/solidity-examples/",
    "/lzapp/", "/oft/", "/uniswap/", "/v3-core/", "/v3-periphery/",
)


def _is_dependency_path(src_file: str | None) -> bool:
    if not src_file:
        return False
    path = ("/" + src_file.lower()).replace("//", "/")
    return any(p in path for p in _NOISY_PATHS + _DEPENDENCY_LIBS)


def _func_def_file(func) -> str | None:
    """The file where the function is actually defined (not the inheriting contract)."""
    try:
        sm = func.source_mapping
        return getattr(sm, "filename_short", None) or getattr(
            getattr(sm, "filename", None), "short", None)
    except Exception:
        return None


def _calls(func) -> tuple[list[str], list[tuple[str, bool]]]:
    """Return (callee names, [(qualified_callee, is_external)])."""
    names: list[str] = []
    edges: list[tuple[str, bool]] = []
    # Internal calls
    for ic in getattr(func, "internal_calls", []) or []:
        target = getattr(ic, "function", None) or ic
        nm = getattr(target, "name", None) or str(ic)
        names.append(nm)
        edges.append((nm, False))
    # High-level (external) calls expose the callee contract + function.
    for hc in getattr(func, "high_level_calls", []) or []:
        # hc is typically a (Contract, Function) tuple across slither versions.
        callee_name = _hlc_name(hc)
        if callee_name:
            names.append(callee_name.split(".")[-1])
            edges.append((callee_name, True))
    # Low-level calls (call/delegatecall/staticcall) are external by nature.
    for lc in getattr(func, "low_level_calls", []) or []:
        names.append(str(getattr(lc, "name", "low_level_call")))
    return names, edges


def _hlc_name(hc) -> str | None:
    try:
        if isinstance(hc, tuple) and len(hc) == 2:
            contract, function = hc
            cn = getattr(contract, "name", None) or str(contract)
            fn = getattr(function, "name", None) or str(function)
            return f"{cn}.{fn}"
        # Newer slither: object with .destination / .function
        fn = getattr(getattr(hc, "function", None), "name", None)
        return fn
    except Exception:
        return None


def _behavioral_facts(func) -> tuple[bool, bool]:
    """(writes_state, makes_external_calls) following internal calls transitively.

    Slither's ``all_*`` accessors fold in callees, so a thin entrypoint that
    delegates to an internal routine is judged on what that routine actually
    does — which is exactly how receiveFromBridge slipped past name-matching.
    """
    writes_state = False
    makes_ext = False
    try:
        writes_state = len(func.all_state_variables_written()) > 0
    except Exception:
        try:
            writes_state = len(func.state_variables_written) > 0
        except Exception:
            pass
    try:
        ext = list(func.all_high_level_calls()) + list(func.all_low_level_calls())
        makes_ext = len(ext) > 0
    except Exception:
        try:
            makes_ext = bool(func.high_level_calls) or bool(func.low_level_calls)
        except Exception:
            pass
    return writes_state, makes_ext


def _confidence(has_structural: bool, has_keyword: bool) -> str:
    if has_structural and has_keyword:
        return "high"
    if has_structural:
        return "structural"
    if has_keyword:
        return "keyword"
    return "none"


def _mutability(func) -> str:
    for attr in ("view", "pure", "payable"):
        if getattr(func, f"{attr}", False):
            return attr
    return "nonpayable"


def _src_file(obj) -> str | None:
    try:
        sm = obj.source_mapping
        return getattr(sm, "filename_short", None) or getattr(
            getattr(sm, "filename", None), "short", None)
    except Exception:
        return None


def _func_line(func) -> int | None:
    try:
        lines = func.source_mapping.lines
        return lines[0] if lines else None
    except Exception:
        return None


def _func_source(func) -> str | None:
    """Best-effort source body for body-level surface matching."""
    try:
        sm = func.source_mapping
        content = getattr(sm, "content", None)
        if content:
            return content
    except Exception:
        pass
    return None
