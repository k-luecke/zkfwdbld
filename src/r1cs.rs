use ark_ff::{One, Zero};

use crate::fields::{F, f64_to_field};
use crate::witness_gen::Clause;

// ---------------------------------------------------------------------------
// Wire index helpers
// ---------------------------------------------------------------------------
// Wire layout (must match SatWitness::to_witness_vec):
//   w = [1,  b_0…b_{n-1},  s_0…s_{m-1},  curvature_score,  t_0…t_{m-1}]
//   idx: 0   1        n    n+1      n+m       n+m+1          n+m+2   n+2m+1
//
// Total wires: n + 2m + 2

const CONST_WIRE: usize = 0;

fn b_wire(i: usize) -> usize {
    1 + i
}
fn s_wire(n: usize, j: usize) -> usize {
    1 + n + j
}
fn score_wire(n: usize, m: usize) -> usize {
    1 + n + m
}
fn t_wire(n: usize, m: usize, j: usize) -> usize {
    2 + n + m + j
}

// ---------------------------------------------------------------------------
// Literal complement helper
// ---------------------------------------------------------------------------
// For literal `lit` over variable b_{var}:
//   Positive lit → y = b_{var}     → (1−y) = w[0] − w[b_wire(var)]
//   Negative lit → y = 1−b_{var}  → (1−y) = w[b_wire(var)]
//
// Returns (wire_index, coefficient) pairs for the (1−y) linear combination.
//
// Precondition: lit != 0  AND  abs(lit) <= num_vars  (caller must validate).

fn lit_complement(lit: i32) -> Vec<(usize, F)> {
    // Safe: caller validates lit != 0, so unsigned_abs() >= 1 and the subtract
    // cannot underflow.
    let var = (lit.unsigned_abs() as usize) - 1;
    let w = b_wire(var);
    if lit > 0 {
        vec![(CONST_WIRE, F::one()), (w, -F::one())]
    } else {
        vec![(w, F::one())]
    }
}

// ---------------------------------------------------------------------------
// Sparse matrix entry helper
// ---------------------------------------------------------------------------

fn push_entries(mat: &mut Vec<(usize, usize, F)>, row: usize, entries: Vec<(usize, F)>) {
    for (col, val) in entries {
        mat.push((row, col, val));
    }
}

// ---------------------------------------------------------------------------
// R1CS instance
// ---------------------------------------------------------------------------

/// A Rank-1 Constraint System over the Goldilocks field.
///
/// Constraint:  (A · w) ∘ (B · w) = (C · w)
///
/// Matrices are stored in coordinate (COO) sparse format: Vec<(row, col, value)>.
pub struct R1CSInstance {
    pub num_vars: usize,
    pub num_clauses: usize,
    pub a: Vec<(usize, usize, F)>,
    pub b: Vec<(usize, usize, F)>,
    pub c: Vec<(usize, usize, F)>,
}

impl R1CSInstance {
    /// Total number of constraint rows: n + 4m + 1.
    ///
    /// Row breakdown (n vars, m clauses):
    ///   n     — Boolean on b_i
    ///   m     — Boolean on s_j
    ///   m     — Clause-1: (1−y_a)·(1−y_b) = t_j
    ///   m     — Clause-2: t_j·(1−y_c) = (1−s_j)
    ///   m     — Satisfaction: s_j·1 = 1  (enforces every clause is satisfied)
    ///   1     — Score constraint
    pub fn num_constraints(&self) -> usize {
        self.num_vars + 4 * self.num_clauses + 1
    }

    /// Total number of wires (columns in A/B/C): n + 2m + 2.
    pub fn num_wires(&self) -> usize {
        self.num_vars + 2 * self.num_clauses + 2
    }

    // -----------------------------------------------------------------------
    // Verify: (A·w) ∘ (B·w) == (C·w)
    // -----------------------------------------------------------------------

    /// Check that witness `w` satisfies all R1CS constraints.
    /// Returns `true` iff every row passes the Hadamard product check.
    pub fn verify(&self, w: &[F]) -> bool {
        if w.len() != self.num_wires() {
            return false;
        }
        let num_rows = self.num_constraints();
        let aw = mat_vec_mul(&self.a, w, num_rows);
        let bw = mat_vec_mul(&self.b, w, num_rows);
        let cw = mat_vec_mul(&self.c, w, num_rows);
        (0..num_rows).all(|i| aw[i] * bw[i] == cw[i])
    }
}

/// Multiply a sparse matrix (COO) by a dense witness vector.
fn mat_vec_mul(mat: &[(usize, usize, F)], w: &[F], num_rows: usize) -> Vec<F> {
    let mut result = vec![F::zero(); num_rows];
    for &(row, col, val) in mat {
        result[row] += val * w[col];
    }
    result
}

// ---------------------------------------------------------------------------
// Constraint builder
// ---------------------------------------------------------------------------

/// Build the R1CS constraint matrices for a 3-SAT instance.
///
/// Returns `Err` if any literal is invalid (zero, or magnitude > num_vars).
/// All other inputs are assumed already validated by the dispatch layer.
///
/// # Row layout (n variables, m clauses)
///
/// | Row range        | Constraint type                           |
/// |------------------|-------------------------------------------|
/// | 0 .. n           | Boolean on b_i:  b_i · (1−b_i) = 0       |
/// | n .. n+m         | Boolean on s_j:  s_j · (1−s_j) = 0       |
/// | n+m .. n+2m      | Clause-1: (1−y_a)·(1−y_b) = t_j          |
/// | n+2m .. n+3m     | Clause-2: t_j·(1−y_c) = (1−s_j)          |
/// | n+3m .. n+4m     | Satisfaction: s_j · 1 = 1  ← NEW          |
/// | n+4m             | Score: curvature_score = Σ coeff_i · b_i  |
pub fn build_sat_constraints(
    cnf: &[Clause],
    num_vars: usize,
    symbolic_field: &[f64],
    entropy_field: &[f64],
) -> Result<R1CSInstance, String> {
    let n = num_vars;
    let m = cnf.len();
    if symbolic_field.len() != n {
        return Err(format!(
            "symbolic_field has length {} but num_vars is {n}",
            symbolic_field.len()
        ));
    }
    if entropy_field.len() != n {
        return Err(format!(
            "entropy_field has length {} but num_vars is {n}",
            entropy_field.len()
        ));
    }

    // Validate all literals before touching any matrix entry.
    for (j, clause) in cnf.iter().enumerate() {
        for &lit in clause.iter() {
            if lit == 0 {
                return Err(format!("clause {j} contains literal 0"));
            }
            let var = lit.unsigned_abs() as usize;
            if var > n {
                return Err(format!(
                    "clause {j}: literal {lit} references variable {var} but num_vars is {n}"
                ));
            }
        }
    }

    let mut a: Vec<(usize, usize, F)> = Vec::new();
    let mut b: Vec<(usize, usize, F)> = Vec::new();
    let mut c: Vec<(usize, usize, F)> = Vec::new();

    let mut row = 0usize;

    // -----------------------------------------------------------------------
    // Boolean constraints on b_i:  b_i · (1 − b_i) = 0
    //   A: b_i
    //   B: (1 − b_i) = w[0] − w[b_wire(i)]
    //   C: 0  (no entries)
    // -----------------------------------------------------------------------
    for i in 0..n {
        let wi = b_wire(i);
        a.push((row, wi, F::one()));
        b.push((row, CONST_WIRE, F::one()));
        b.push((row, wi, -F::one()));
        row += 1;
    }

    // -----------------------------------------------------------------------
    // Boolean constraints on s_j:  s_j · (1 − s_j) = 0
    //   A: s_j
    //   B: (1 − s_j)
    //   C: 0
    // -----------------------------------------------------------------------
    for j in 0..m {
        let wj = s_wire(n, j);
        a.push((row, wj, F::one()));
        b.push((row, CONST_WIRE, F::one()));
        b.push((row, wj, -F::one()));
        row += 1;
    }

    // -----------------------------------------------------------------------
    // Clause-1:  (1 − y_a) · (1 − y_b) = t_j
    //
    //   A: (1 − y_a)  — from lit_complement(clause[0])
    //   B: (1 − y_b)  — from lit_complement(clause[1])
    //   C: t_j
    // -----------------------------------------------------------------------
    for (j, clause) in cnf.iter().enumerate() {
        let tw = t_wire(n, m, j);
        push_entries(&mut a, row, lit_complement(clause[0]));
        push_entries(&mut b, row, lit_complement(clause[1]));
        c.push((row, tw, F::one()));
        row += 1;
    }

    // -----------------------------------------------------------------------
    // Clause-2:  t_j · (1 − y_c) = (1 − s_j)
    //
    //   A: t_j
    //   B: (1 − y_c)  — from lit_complement(clause[2])
    //   C: (1 − s_j) = w[0] − w[s_wire(j)]
    //
    // If clause SAT: ≥1 literal true → (1−y_a)(1−y_b)(1−y_c)=0 → (1−s_j)=0 → s_j=1
    // If clause UNSAT: all false → t_j=1, (1−y_c)=1 → (1−s_j)=1 → s_j=0
    // -----------------------------------------------------------------------
    for (j, clause) in cnf.iter().enumerate() {
        let tw = t_wire(n, m, j);
        let sw = s_wire(n, j);
        a.push((row, tw, F::one()));
        push_entries(&mut b, row, lit_complement(clause[2]));
        c.push((row, CONST_WIRE, F::one()));
        c.push((row, sw, -F::one()));
        row += 1;
    }

    // -----------------------------------------------------------------------
    // Satisfaction constraints:  s_j · 1 = 1   (one row per clause)
    //
    // The Boolean + clause constraints above allow s_j ∈ {0, 1} and relate
    // s_j to the clause literals, but they do NOT force s_j = 1.
    // Without this block a witness where s_j = 0 (clause UNSAT) would pass
    // the Hadamard check, making the proof unsound.
    //
    //   A: s_j     (wire s_wire(n, j))
    //   B: 1       (const wire)
    //   C: 1       (const wire)
    //
    // Enforces:  s_j * 1 = 1  →  s_j = 1
    // -----------------------------------------------------------------------
    for j in 0..m {
        let sw = s_wire(n, j);
        a.push((row, sw, F::one()));
        b.push((row, CONST_WIRE, F::one()));
        c.push((row, CONST_WIRE, F::one()));
        row += 1;
    }

    // -----------------------------------------------------------------------
    // Score constraint:  curvature_score · 1 = Σ_i coeff_i · b_i + offset
    //
    // score  = Σ_i sym[i]·b_i  −  Σ_i ent[i]·(1−b_i)
    //        = Σ_i (sym[i]+ent[i])·b_i  −  Σ_i ent[i]
    //
    //   A: curvature_score wire
    //   B: w[0] = 1  (identity multiplication)
    //   C: Σ_i scale(sym[i]+ent[i])·b_i  +  (−Σ_i scale(ent[i]))·w[0]
    // -----------------------------------------------------------------------
    {
        let sw = score_wire(n, m);
        a.push((row, sw, F::one()));
        b.push((row, CONST_WIRE, F::one()));

        let const_offset = entropy_field
            .iter()
            .fold(F::zero(), |acc, &e| acc - f64_to_field(e));
        c.push((row, CONST_WIRE, const_offset));

        for i in 0..n {
            let coeff = f64_to_field(symbolic_field[i] + entropy_field[i]);
            c.push((row, b_wire(i), coeff));
        }

        row += 1;
    }

    // Runtime check (not debug_assert!): release builds set `panic = "abort"`
    // and strip debug assertions, so a future builder change that mis-counts
    // rows would silently produce a malformed R1CS in production. Return an
    // error so the dispatch layer can surface it.
    let expected = n + 4 * m + 1;
    if row != expected {
        return Err(format!(
            "internal error: row count mismatch (got {row}, expected {expected})"
        ));
    }

    Ok(R1CSInstance {
        num_vars: n,
        num_clauses: m,
        a,
        b,
        c,
    })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::witness_gen::{generate_fields, generate_witness};
    use ark_ff::Zero;

    /// (x1 ∨ x2 ∨ ¬x3) ∧ (¬x1 ∨ x2 ∨ x3)
    fn trivial_cnf() -> Vec<Clause> {
        vec![[1, 2, -3], [-1, 2, 3]]
    }

    const SEED: u64 = 42;

    #[test]
    fn verify_passes_for_valid_witness() {
        let cnf = trivial_cnf();
        let num_vars = 3;
        let witness = generate_witness(&cnf, num_vars, SEED).expect("SAT");
        let (sym, ent) = generate_fields(num_vars, SEED);
        let r1cs = build_sat_constraints(&cnf, num_vars, &sym, &ent).unwrap();
        let w = witness.to_witness_vec();
        assert!(r1cs.verify(&w), "valid witness failed verification");
    }

    #[test]
    fn wire_and_constraint_counts() {
        let cnf = trivial_cnf();
        let num_vars = 3;
        let (sym, ent) = generate_fields(num_vars, SEED);
        let r1cs = build_sat_constraints(&cnf, num_vars, &sym, &ent).unwrap();
        // n=3, m=2: wires = 3+2*2+2 = 9; constraints = 3+4*2+1 = 12
        assert_eq!(r1cs.num_wires(), 9);
        assert_eq!(r1cs.num_constraints(), 12);
    }

    #[test]
    fn tampered_assignment_fails_verify() {
        let cnf = trivial_cnf();
        let num_vars = 3;
        let witness = generate_witness(&cnf, num_vars, SEED).expect("SAT");
        let (sym, ent) = generate_fields(num_vars, SEED);
        let r1cs = build_sat_constraints(&cnf, num_vars, &sym, &ent).unwrap();
        let mut w = witness.to_witness_vec();
        // Flip the first boolean variable wire.
        w[1] = if w[1] == F::zero() {
            F::one()
        } else {
            F::zero()
        };
        assert!(!r1cs.verify(&w), "tampered witness should fail");
    }

    #[test]
    fn wrong_witness_length_fails_verify_not_panic() {
        let cnf = trivial_cnf();
        let num_vars = 3;
        let (sym, ent) = generate_fields(num_vars, SEED);
        let r1cs = build_sat_constraints(&cnf, num_vars, &sym, &ent).unwrap();
        let short_witness = vec![F::one(); r1cs.num_wires() - 1];
        assert!(!r1cs.verify(&short_witness));
    }

    #[test]
    fn unsat_witness_rejected_by_s_j_constraint() {
        // (x1 ∨ x1 ∨ x1) — always SAT if x1=true, so build an UNSAT instance:
        // (x1 ∨ x1 ∨ x1) ∧ (¬x1 ∨ ¬x1 ∨ ¬x1)
        // Manually craft a witness where s_0=0 (first clause "unsatisfied") and
        // verify it is rejected by the new s_j=1 constraint.
        let cnf = trivial_cnf();
        let num_vars = 3;
        let witness = generate_witness(&cnf, num_vars, SEED).expect("SAT");
        let (sym, ent) = generate_fields(num_vars, SEED);
        let r1cs = build_sat_constraints(&cnf, num_vars, &sym, &ent).unwrap();
        let mut w = witness.to_witness_vec();
        // Force s_0 = 0 (clause-0 "unsatisfied").
        // Wire index: 1 + num_vars + 0  =  1 + 3 + 0  =  4
        w[4] = F::zero();
        assert!(
            !r1cs.verify(&w),
            "witness with s_j=0 must be rejected by the satisfaction constraint"
        );
    }

    /// Corrupt a `t_j` intermediate wire while keeping `s_j = 1`.
    ///
    /// The existing `unsat_witness_rejected_by_s_j_constraint` test directly
    /// zeroes the satisfaction wire — the *terminal* constraint.  This test goes
    /// one level deeper: it corrupts the *intermediate product wire* `t_0` that
    /// feeds into the Clause-1 and Clause-2 constraints, while leaving `s_0 = 1`
    /// so the satisfaction row still looks valid.
    ///
    /// Clause-1 enforces  (1−y_a)·(1−y_b) = t_j.
    /// Any value of t_j inconsistent with the literal evaluation violates that
    /// row, proving that the soundness guarantee comes from the full literal-
    /// evaluation path, not just the terminal s_j = 1 constraint.
    ///
    /// Wire layout reminder (n=3, m=2):
    ///   w[0]=1  w[1]=b0  w[2]=b1  w[3]=b2
    ///   w[4]=s0  w[5]=s1  w[6]=score  w[7]=t0  w[8]=t1
    #[test]
    fn corrupted_t_wire_caught_by_clause_constraints() {
        let cnf = trivial_cnf();
        let num_vars = 3;
        let witness = generate_witness(&cnf, num_vars, SEED).expect("SAT");
        let (sym, ent) = generate_fields(num_vars, SEED);
        let r1cs = build_sat_constraints(&cnf, num_vars, &sym, &ent).unwrap();
        let mut w = witness.to_witness_vec();

        // Confirm valid before corruption.
        assert!(r1cs.verify(&w), "pre-condition: valid witness must pass");

        // t_0 is at index t_wire(n=3, m=2, j=0) = 2 + 3 + 2 + 0 = 7.
        // s_0 is at index s_wire(n=3, j=0) = 1 + 3 + 0 = 4.
        // Flip t_0 to its complement (0↔1). s_0 stays 1 — the satisfaction
        // constraint sees s_0·1=1 and is satisfied. Only Clause-1 / Clause-2
        // will detect the inconsistency between t_0 and the literal values.
        let t0_idx = 2 + num_vars + 2 + 0; // = 7
        w[t0_idx] = if w[t0_idx] == F::zero() {
            F::one()
        } else {
            F::zero()
        };

        // s_0 must still be 1 to isolate the clause constraint, not the
        // satisfaction constraint, as the failure origin.
        let s0_idx = 1 + num_vars + 0; // = 4
        w[s0_idx] = F::one();

        assert!(
            !r1cs.verify(&w),
            "corrupted t_j must be caught by Clause-1/2 constraints, \
             independent of the s_j=1 satisfaction row"
        );
    }

    /// Non-boolean variable value (b_i = 2) must fail the Boolean constraint.
    ///
    /// Boolean constraint row for variable i:  b_i · (1 − b_i) = 0.
    /// With b_i = 2:  2 · (1 − 2) = 2 · (−1) = −2 ≠ 0 → row fails.
    ///
    /// This test verifies that the R1CS rejects witnesses with non-{0,1} wire
    /// values even when every other wire remains valid.
    #[test]
    fn non_boolean_variable_rejected() {
        let cnf = trivial_cnf();
        let num_vars = 3;
        let witness = generate_witness(&cnf, num_vars, SEED).expect("SAT");
        let (sym, ent) = generate_fields(num_vars, SEED);
        let r1cs = build_sat_constraints(&cnf, num_vars, &sym, &ent).unwrap();
        let mut w = witness.to_witness_vec();

        // b_0 is at wire index 1.  Set it to 2 (outside {0, 1}).
        w[1] = F::from(2u64);

        assert!(
            !r1cs.verify(&w),
            "non-boolean input b_i=2 must be caught by the Boolean constraint"
        );
    }

    /// Genuinely UNSAT formula — fake witness claiming all clauses satisfied.
    ///
    /// Formula: (x1 ∨ x1 ∨ x1) ∧ (¬x1 ∨ ¬x1 ∨ ¬x1), 1 variable.
    /// This is UNSAT: x1=1 falsifies clause 2; x1=0 falsifies clause 1.
    ///
    /// Wire layout (n=1, m=2):
    ///   w[0]=1  w[1]=b0  w[2]=s0  w[3]=s1  w[4]=score  w[5]=t0  w[6]=t1
    ///
    /// Attack: set b0=1, s0=1, s1=1 (lying about clause 2), and choose t0/t1
    /// that appear self-consistent.  The clause product constraints must reject.
    ///
    /// With b0=1 (x1=true):
    ///   Clause 2 (¬x1 ∨ ¬x1 ∨ ¬x1): y_a=y_b=y_c = 1−b0 = 0
    ///     (1−y_a)=1, (1−y_b)=1, (1−y_c)=1
    ///   Clause-1: 1·1 = 1 → t1 must equal 1
    ///   Clause-2: 1·1 = (1−s1)  →  if s1=1 then 0 ≠ 1  → FAILS
    #[test]
    fn genuinely_unsat_fake_witness_rejected() {
        // (x1 ∨ x1 ∨ x1) ∧ (¬x1 ∨ ¬x1 ∨ ¬x1)
        let cnf: Vec<Clause> = vec![[1, 1, 1], [-1, -1, -1]];
        let num_vars = 1;
        let (sym, ent) = generate_fields(num_vars, SEED);
        let r1cs = build_sat_constraints(&cnf, num_vars, &sym, &ent).unwrap();

        // n=1, m=2 → wires = 1+2*2+2 = 7
        assert_eq!(r1cs.num_wires(), 7);

        // Craft the most optimistic fake witness: b0=1, all s_j=1.
        // t0: clause 1 (x1∨x1∨x1) with b0=1 → y_a=y_b=y_c=1 → (1-y)=0 → t0=0
        // t1: clause 2 (¬x1∨¬x1∨¬x1) with b0=1 → y=1-1=0 → (1-y)=1 → t1=1*1=1
        // With s1=1, Clause-2 for clause 2 requires: t1*(1-y_c)=(1-s1)=0
        //   → 1*1=1 ≠ 0 → constraint fails regardless of our fake s1=1.
        let score_wire_idx = 1 + num_vars + 2; // = 4
        let (sym_val, ent_val) = (sym[0], ent[0]);
        // score = sym[0]*b0 - ent[0]*(1-b0) = sym[0] - 0 (with b0=1)
        let score =
            crate::fields::f64_to_field(sym_val + ent_val) - crate::fields::f64_to_field(ent_val);

        let mut w = vec![F::zero(); r1cs.num_wires()];
        w[0] = F::one(); // constant
        w[1] = F::one(); // b0 = 1 (x1 = true)
        w[2] = F::one(); // s0 = 1 (fake: clause 1 "satisfied")
        w[3] = F::one(); // s1 = 1 (fake: clause 2 "satisfied")
        w[score_wire_idx] = score; // score wire
        w[5] = F::zero(); // t0 = 0 (clause 1 with b0=1: (1-1)*(1-1)=0)
        w[6] = F::one(); // t1 = 1 (clause 2 with b0=1: (1-0)*(1-0)=1)

        assert!(
            !r1cs.verify(&w),
            "fake witness for UNSAT formula must be rejected by clause-2 constraint"
        );
    }

    #[test]
    fn zero_literal_returns_error() {
        let cnf: Vec<Clause> = vec![[0, 1, 2]];
        let (sym, ent) = generate_fields(3, SEED);
        assert!(build_sat_constraints(&cnf, 3, &sym, &ent).is_err());
    }

    #[test]
    fn out_of_range_literal_returns_error() {
        let cnf: Vec<Clause> = vec![[1, 2, 99]];
        let (sym, ent) = generate_fields(3, SEED);
        assert!(build_sat_constraints(&cnf, 3, &sym, &ent).is_err());
    }

    /// The builder's terminal row count must equal `num_constraints()` for
    /// every legal (n, m). This guards against the original M-12 hazard:
    /// a future builder change that pushes the wrong number of rows would
    /// otherwise silently produce a malformed R1CS in release (where
    /// `debug_assert!` is stripped and `panic = "abort"` is set).
    #[test]
    fn builder_row_count_matches_num_constraints_invariant() {
        // Several (num_vars, num_clauses) shapes. Clauses are valid literals
        // bounded by num_vars; concrete satisfiability is irrelevant here —
        // we only care that build_sat_constraints completes successfully and
        // that the row-count invariant n + 4m + 1 holds end-to-end.
        let cases: &[(usize, Vec<Clause>)] = &[
            (1, vec![[1, 1, 1]]),
            (3, vec![[1, 2, -3], [-1, 2, 3]]),
            (5, vec![[1, -2, 3], [4, -5, 1], [-3, 2, 5], [1, 4, -2]]),
        ];
        for (num_vars, cnf) in cases {
            let (sym, ent) = generate_fields(*num_vars, SEED);
            let r1cs = build_sat_constraints(cnf, *num_vars, &sym, &ent)
                .expect("build_sat_constraints must succeed for valid inputs");
            assert_eq!(
                r1cs.num_constraints(),
                num_vars + 4 * cnf.len() + 1,
                "row-count invariant violated for n={num_vars}, m={}",
                cnf.len()
            );
        }
    }

    #[test]
    fn field_length_mismatch_returns_error() {
        let cnf = trivial_cnf();
        let (_sym, ent) = generate_fields(3, SEED);
        let short_sym = vec![0.0, 1.0];
        assert!(build_sat_constraints(&cnf, 3, &short_sym, &ent).is_err());
    }
}
