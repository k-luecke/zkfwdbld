use ark_ff::{One, Zero};
use ark_std::rand::rngs::StdRng;
use ark_std::rand::{Rng, SeedableRng};

use crate::fields::{F, f64_to_field};

/// A 3-SAT clause: three signed literals, 1-indexed.
/// Positive literal  →  variable must be True.
/// Negative literal  →  variable must be False.
pub type Clause = [i32; 3];

// ---------------------------------------------------------------------------
// Witness struct
// ---------------------------------------------------------------------------

/// Full R1CS witness for a 3-SAT instance solved via the curvature heuristic.
///
/// Flat wire layout produced by `to_witness_vec`:
///   w = [1,  b_0…b_{n-1},  s_0…s_{m-1},  curvature_score,  t_0…t_{m-1}]
///        ↑   ←── n ──→     ←─── m ───→        ↑             ←── m ──→
///      const  bool vars   clause bits         score       intermediate products
///
/// Total wires: n + 2m + 2
pub struct SatWitness {
    /// b_i ∈ {0,1} — satisfying Boolean assignment, one field element per variable.
    pub assignments: Vec<F>,
    /// s_j ∈ {0,1} — clause satisfaction bit, one field element per clause.
    pub clause_bits: Vec<F>,
    /// Curvature-weighted score of the chosen assignment, 2^32 fixed-point encoded.
    pub curvature_score: F,
    /// t_j = (1 − y_a)(1 − y_b) for clause j — intermediate product wires needed
    /// by the R1CS clause constraints (Clause-1 row output / Clause-2 row input).
    pub intermediate_wires: Vec<F>,
}

impl SatWitness {
    /// Flatten into a dense `Vec<F>` in Spartan R1CS wire order:
    ///   [1, assignments, clause_bits, curvature_score, intermediate_wires]
    pub fn to_witness_vec(&self) -> Vec<F> {
        let cap =
            1 + self.assignments.len() + self.clause_bits.len() + 1 + self.intermediate_wires.len();
        let mut w = Vec::with_capacity(cap);
        w.push(F::one());
        w.extend_from_slice(&self.assignments);
        w.extend_from_slice(&self.clause_bits);
        w.push(self.curvature_score);
        w.extend_from_slice(&self.intermediate_wires);
        w
    }
}

// ---------------------------------------------------------------------------
// Gaussian smoothing (1-D)
// Mimics scipy.ndimage.gaussian_filter(x, sigma) on a 1-D array.
// Uses a truncated discrete Gaussian kernel (half-width = ceil(3σ)) with
// reflect boundary padding — identical to scipy's default mode.
// ---------------------------------------------------------------------------

pub(crate) fn gaussian_smooth_1d(input: &[f64], sigma: f64) -> Vec<f64> {
    let half = (3.0 * sigma).ceil() as usize;
    let kernel_len = 2 * half + 1;

    let mut kernel = Vec::with_capacity(kernel_len);
    for x in -(half as i64)..=(half as i64) {
        kernel.push((-(x * x) as f64 / (2.0 * sigma * sigma)).exp());
    }
    let sum: f64 = kernel.iter().sum();
    kernel.iter_mut().for_each(|k| *k /= sum);

    let n = input.len();
    let mut output = vec![0.0f64; n];
    for i in 0..n {
        let mut acc = 0.0f64;
        for (ki, &kval) in kernel.iter().enumerate() {
            let offset = ki as i64 - half as i64;
            let mut j = i as i64 + offset;
            if j < 0 {
                j = -j - 1;
            } else if j >= n as i64 {
                j = 2 * n as i64 - j - 1;
            }
            let j = (j as usize).min(n - 1);
            acc += input[j] * kval;
        }
        output[i] = acc;
    }
    output
}

// ---------------------------------------------------------------------------
// Field generation — exposed so the R1CS builder can reconstruct the exact
// same symbolic and entropy fields for a given (num_vars, seed) pair.
// ---------------------------------------------------------------------------

/// Generate and Gaussian-smooth the symbolic and entropy fields.
/// Returns `(symbolic_field, entropy_field)`, each of length `num_vars`.
/// Call this with the same seed used for `generate_witness` to obtain the
/// field coefficients needed by `r1cs::build_sat_constraints`.
pub fn generate_fields(num_vars: usize, seed: u64) -> (Vec<f64>, Vec<f64>) {
    let mut rng = StdRng::seed_from_u64(seed);
    let raw_sym: Vec<f64> = (0..num_vars).map(|_| rng.r#gen::<f64>()).collect();
    let raw_ent: Vec<f64> = (0..num_vars).map(|_| rng.r#gen::<f64>()).collect();
    (
        gaussian_smooth_1d(&raw_sym, 1.0),
        gaussian_smooth_1d(&raw_ent, 1.0),
    )
}

// ---------------------------------------------------------------------------
// Core witness generator
// ---------------------------------------------------------------------------

/// Solve `cnf` using the Gaussian-smoothed symbolic curvature heuristic and
/// return a fully populated `SatWitness`, or `None` if the instance is UNSAT.
///
/// Callers MUST validate that `num_vars <= 26` before calling; this function
/// will return `None` (treating it as UNSAT) rather than panic on invalid input,
/// but the exhaustive 2^n search is only tractable up to ~26 variables.
///
/// Algorithm:
///  1. Generate symbolic and entropy fields via `generate_fields(num_vars, seed)`.
///  2. Exhaustively enumerate all 2^n assignments; discard UNSAT ones.
///  3. Among satisfying assignments, select the one maximising the curvature score.
///  4. Pack into a `SatWitness` ready for `to_witness_vec`.
pub fn generate_witness(cnf: &[Clause], num_vars: usize, seed: u64) -> Option<SatWitness> {
    // Guard: exhaustive search beyond 26 variables would run for minutes or
    // exhaust Wasm linear memory. Return None (treated as UNSAT by the caller)
    // rather than panic — the dispatch layer rejects oversized inputs before
    // reaching here, so this is a belt-and-suspenders check only.
    if num_vars == 0 || num_vars > 26 {
        return None;
    }

    let (symbolic_field, entropy_field) = generate_fields(num_vars, seed);

    // Evaluate literal truth value from a bitmask assignment.
    let eval_lit = |lit: i32, mask: u64| -> bool {
        // Safe: lit validated by dispatch (non-zero, |lit| <= num_vars <= 26)
        let var = (lit.unsigned_abs() as usize) - 1;
        let is_true = (mask >> var) & 1 == 1;
        if lit > 0 { is_true } else { !is_true }
    };

    // Exhaustive scored search.
    let mut best_score = f64::NEG_INFINITY;
    let mut best_mask: Option<u64> = None;

    for mask in 0u64..(1u64 << num_vars) {
        let score: f64 = (0..num_vars)
            .map(|i| {
                if (mask >> i) & 1 == 1 {
                    symbolic_field[i]
                } else {
                    -entropy_field[i]
                }
            })
            .sum();

        let satisfies = cnf
            .iter()
            .all(|clause| clause.iter().any(|&lit| eval_lit(lit, mask)));

        if satisfies && score > best_score {
            best_score = score;
            best_mask = Some(mask);
        }
    }

    let mask = best_mask?; // None → UNSAT

    // b_i wires
    let assignments: Vec<F> = (0..num_vars)
        .map(|i| {
            if (mask >> i) & 1 == 1 {
                F::one()
            } else {
                F::zero()
            }
        })
        .collect();

    // s_j wires
    let clause_bits: Vec<F> = cnf
        .iter()
        .map(|clause| {
            if clause.iter().any(|&lit| eval_lit(lit, mask)) {
                F::one()
            } else {
                F::zero()
            }
        })
        .collect();

    // t_j = (1 − y_a)(1 − y_b) — intermediate product for the first two literals.
    let intermediate_wires: Vec<F> = cnf
        .iter()
        .map(|clause| {
            let ya = eval_lit(clause[0], mask);
            let yb = eval_lit(clause[1], mask);
            if !ya && !yb { F::one() } else { F::zero() }
        })
        .collect();

    // Encode curvature_score using the exact same per-element field arithmetic
    // that build_sat_constraints uses in the C matrix so the score constraint
    // passes verification bit-for-bit.
    let curvature_score = {
        let offset = entropy_field
            .iter()
            .fold(F::zero(), |acc, &e| acc - f64_to_field(e));
        let var_contrib = (0..num_vars)
            .filter(|&i| (mask >> i) & 1 == 1)
            .fold(F::zero(), |acc, i| {
                acc + f64_to_field(symbolic_field[i] + entropy_field[i])
            });
        offset + var_contrib
    };

    Some(SatWitness {
        assignments,
        clause_bits,
        curvature_score,
        intermediate_wires,
    })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// (x1 ∨ x2 ∨ ¬x3) ∧ (¬x1 ∨ x2 ∨ x3)
    fn trivial_cnf() -> Vec<Clause> {
        vec![[1, 2, -3], [-1, 2, 3]]
    }

    fn n() -> usize {
        3
    }
    fn m() -> usize {
        2
    }

    #[test]
    fn clause_bits_all_one() {
        let cnf = trivial_cnf();
        let w = generate_witness(&cnf, n(), 42).expect("should be SAT");
        for (j, &bit) in w.clause_bits.iter().enumerate() {
            assert_eq!(bit, F::one(), "clause {j} not satisfied");
        }
    }

    #[test]
    fn witness_vec_length() {
        let cnf = trivial_cnf();
        let w = generate_witness(&cnf, n(), 42).unwrap().to_witness_vec();
        // 1 + n + m + 1 + m  =  1 + 3 + 2 + 1 + 2  =  9
        assert_eq!(w.len(), 1 + n() + m() + 1 + m());
        assert_eq!(w[0], F::one(), "wire 0 must be the constant 1");
    }

    #[test]
    fn assignments_are_boolean() {
        let cnf = trivial_cnf();
        let w = generate_witness(&cnf, n(), 42).unwrap();
        for &b in &w.assignments {
            assert!(b == F::zero() || b == F::one());
        }
    }

    #[test]
    fn intermediate_wires_are_boolean() {
        let cnf = trivial_cnf();
        let w = generate_witness(&cnf, n(), 42).unwrap();
        for &t in &w.intermediate_wires {
            assert!(t == F::zero() || t == F::one());
        }
    }

    #[test]
    fn unsat_returns_none() {
        // (x1) ∧ (¬x1) — unsatisfiable, padded to clause width 3.
        let cnf: Vec<Clause> = vec![[1, 1, 1], [-1, -1, -1]];
        assert!(generate_witness(&cnf, 1, 0).is_none());
    }

    #[test]
    fn oversized_num_vars_returns_none_not_panic() {
        let cnf: Vec<Clause> = vec![[1, 2, 3]];
        // 27 > MAX — must return None, not panic
        assert!(generate_witness(&cnf, 27, 0).is_none());
    }
}
