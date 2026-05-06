use std::time::Instant;

use zkfwdbld::r1cs::build_sat_constraints;
use zkfwdbld::witness_gen::{Clause, generate_fields, generate_witness};

struct XorShift64(u64);

impl XorShift64 {
    fn new(seed: u64) -> Self {
        Self(seed.max(1))
    }

    fn next_u64(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.0 = x;
        x
    }

    fn range(&mut self, upper: usize) -> usize {
        (self.next_u64() as usize) % upper
    }

    fn coin(&mut self) -> bool {
        self.next_u64() & 1 == 1
    }
}

fn lit_for_assignment(var: usize, target_mask: u64, satisfied: bool) -> i32 {
    let value_is_true = (target_mask >> (var - 1)) & 1 == 1;
    let positive_lit_is_satisfied = value_is_true;
    if positive_lit_is_satisfied == satisfied {
        var as i32
    } else {
        -(var as i32)
    }
}

fn satisfiable_cnf(num_vars: usize, num_clauses: usize, seed: u64) -> Vec<Clause> {
    let mut rng = XorShift64::new(seed);
    let target_mask = rng.next_u64() & ((1u64 << num_vars) - 1);

    (0..num_clauses)
        .map(|_| {
            let satisfied_slot = rng.range(3);
            let mut clause = [0i32; 3];
            for (slot, lit) in clause.iter_mut().enumerate() {
                let var = 1 + rng.range(num_vars);
                *lit = lit_for_assignment(var, target_mask, slot == satisfied_slot || rng.coin());
            }
            clause
        })
        .collect()
}

fn run_case(num_vars: usize, num_clauses: usize, seed: u64) {
    let cnf = satisfiable_cnf(num_vars, num_clauses, seed);

    let t0 = Instant::now();
    let witness = generate_witness(&cnf, num_vars, seed).expect("generated CNF should be SAT");
    let witness_ms = t0.elapsed().as_secs_f64() * 1000.0;

    let (sym, ent) = generate_fields(num_vars, seed);
    let t1 = Instant::now();
    let r1cs = build_sat_constraints(&cnf, num_vars, &sym, &ent).expect("valid generated CNF");
    let build_ms = t1.elapsed().as_secs_f64() * 1000.0;

    let w = witness.to_witness_vec();
    let t2 = Instant::now();
    let valid = r1cs.verify(&w);
    let verify_ms = t2.elapsed().as_secs_f64() * 1000.0;

    println!(
        "{num_vars},{num_clauses},{seed},{},{},{witness_ms:.3},{build_ms:.3},{verify_ms:.3},{valid}",
        r1cs.num_constraints(),
        r1cs.num_wires()
    );
}

// Audit I-9 (#44): the previous version reported a single timing per
// (num_vars, num_clauses) tuple at seed=42, with no variance estimate. Use a
// dense `(0..NUM_SEEDS)` sweep so a downstream CSV consumer can compute
// per-cell median/MAD without picking arbitrary primes that bias toward
// "interesting" XorShift trajectories.
const NUM_SEEDS: u64 = 5;

fn main() {
    println!("num_vars,num_clauses,seed,constraints,wires,witness_ms,build_ms,verify_ms,valid");

    for &(num_vars, num_clauses) in &[
        (8, 64),
        (12, 64),
        (16, 64),
        (18, 64),
        (20, 64),
        (12, 256),
        (12, 1024),
        (12, 4096),
    ] {
        for seed in 0..NUM_SEEDS {
            run_case(num_vars, num_clauses, seed);
        }
    }
}
