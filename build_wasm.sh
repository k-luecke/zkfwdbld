#!/usr/bin/env bash
# build_wasm.sh — Tape-out script for the zkfwdbld AO Prover module.
# Produces a stripped .wasm binary ready for `aoloader deploy`.

set -euo pipefail

TARGET="wasm32-unknown-unknown"
CRATE_OUT="zkfwdbld"           # matches [package] name in Cargo.toml (Rust lowercases it)
OUT_DIR="target/${TARGET}/release"
WASM="${OUT_DIR}/${CRATE_OUT}.wasm"

echo "── Step 1: Ensure Wasm target is installed ─────────────────────────────"
rustup target add "${TARGET}"

echo "── Step 2: Compile (release profile: lto=true, opt-level=z, panic=abort)"
cargo build --target "${TARGET}" --release

echo "── Step 3: Strip debug/name sections with wasm-strip ───────────────────"
if command -v wasm-strip &>/dev/null; then
    BEFORE=$(wc -c < "${WASM}")
    wasm-strip "${WASM}"
    AFTER=$(wc -c < "${WASM}")
    echo "  ${BEFORE} bytes → ${AFTER} bytes (saved $((BEFORE - AFTER)) bytes)"
else
    echo "  WARNING: wasm-strip not found. Install wabt:"
    echo "    apt install wabt   OR   brew install wabt"
    echo "  Continuing with unstripped binary."
fi

echo ""
echo "── Output ──────────────────────────────────────────────────────────────"
ls -lh "${WASM}"
echo ""
echo "Deploy with:  aoloader deploy ${WASM}"
