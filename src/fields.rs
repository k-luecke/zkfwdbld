// ark-ff 0.4.x's MontConfig derive wraps its generated impl in an internal
// function, which triggers Rust's non_local_definitions lint. This is a known
// macro bug fixed in later ark-ff versions; suppress it here until upgraded.
#![allow(non_local_definitions)]

use ark_ff::{Fp64, MontBackend, MontConfig};

/// Goldilocks prime: p = 2^64 - 2^32 + 1 = 18446744069414584321
/// This is the standard 64-bit prime used in Plonky2 and related provers.
/// p - 1 = 2^32 * (2^32 - 1), giving a large 2-adicity for FFT-friendly arithmetic.
#[derive(MontConfig)]
#[modulus = "18446744069414584321"]
#[generator = "7"]
pub struct GoldilocksConfig;

/// The Goldilocks field element type (single-limb Montgomery form).
pub type F = Fp64<MontBackend<GoldilocksConfig, 1>>;

/// Fixed-point scale for encoding f64 scores as field elements.
/// Multiplying by 2^32 preserves ~9 decimal digits of fractional precision.
pub const SCORE_SCALE: f64 = 4_294_967_296.0; // 2^32

/// Encode a signed f64 as a Goldilocks field element using 2^32 fixed-point.
/// Positive values  →  F::from(scaled_u64)
/// Negative values  →  additive inverse in F_p  (p − |scaled_u64|)
pub fn f64_to_field(x: f64) -> F {
    let scaled = (x * SCORE_SCALE).round();
    if scaled >= 0.0 {
        F::from(scaled as u64)
    } else {
        -F::from((-scaled) as u64)
    }
}
