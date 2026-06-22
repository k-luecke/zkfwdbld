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
from .surface import tag_surfaces


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


def run_slither(target: Path) -> SlitherExtract:
    """Run Slither over ``target`` (a project dir or a single .sol file)."""
    from slither import Slither  # imported lazily so the package loads without it

    sl = Slither(str(target))

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
            full = func.full_name  # name(arg types)
            callees, ext_edges = _calls(func)
            for callee, is_ext in ext_edges:
                edges.append(CallEdge(
                    caller=f"{contract.name}.{func.name}",
                    callee=callee,
                    external=is_ext,
                ))
            surfaces = tag_surfaces(
                function_name=func.name,
                callees=callees,
                source_body=_func_source(func),
                modifiers=[m.name for m in func.modifiers],
            )
            fi = FunctionInfo(
                contract=contract.name,
                name=func.name,
                signature=full,
                visibility=func.visibility,
                mutability=_mutability(func),
                modifiers=[m.name for m in func.modifiers],
                is_entry_point=True,
                surfaces=list(surfaces.keys()),
                surface_evidence=surfaces,
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
    path = ("/" + (_src_file(contract) or "").lower()).replace("//", "/")
    noisy_paths = ("/test/", "/tests/", "/script/", "/mock", "/node_modules/")
    dependency_libs = (
        "/forge-std/", "/openzeppelin-contracts", "/openzeppelin/", "/solmate/",
        "/solady/", "/ds-test/", "/permit2/", "/prb-math/", "/erc4626-tests/",
        "/createx/", "/layerzero", "/lz-evm",
    )
    if any(p in path for p in noisy_paths + dependency_libs):
        return True
    if name.endswith("test") or name.endswith("mock") or name.startswith("mock"):
        return True
    return False


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
