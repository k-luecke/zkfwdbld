pub mod fields;
pub mod r1cs;
pub mod witness_gen;

use std::alloc::Layout;

use ark_ff::PrimeField;
use serde::{Deserialize, Serialize};

use crate::fields::F;
use crate::r1cs::build_sat_constraints;
use crate::witness_gen::{Clause, generate_fields, generate_witness};

// ── Supported limits ─────────────────────────────────────────────────────────

/// Maximum number of SAT variables allowed.
/// Exhaustive search is 2^n — 26 keeps runtime under ~1 second.
pub const MAX_VARS: usize = 26;
/// Maximum number of 3-SAT clauses accepted in one request.
/// Work is O(2^num_vars * clauses), and R1CS memory is O(clauses).
const MAX_CLAUSES: usize = 4096;
/// Maximum inbound JSON payload accepted by the raw Wasm ABI.
const MAX_INPUT_BYTES: usize = 1_048_576;

// ── JSON message types ────────────────────────────────────────────────────────
// AO + Lua sends UTF-8 JSON. The `Action` field is the discriminant tag.
//
// Prove  → run curvature heuristic, return witness bytes if SAT.
// Verify → check a previously returned witness against the R1CS.

#[derive(Serialize, Deserialize)]
#[serde(tag = "Action")]
pub enum Request {
    Prove {
        cnf: Vec<Vec<i32>>,
        num_vars: usize,
        seed: Option<u64>,
        /// AO metadata — accepted but not used by the kernel.
        /// `fact` is always a plain string from the Lua orchestrator.
        fact: Option<String>,
        /// `context` is a JSON-encoded string from Lua (the orchestrator
        /// double-encodes it so serde can deserialize it as Option<String>).
        /// Declared as Value so a future schema change in the orchestrator
        /// (sending a bare object) does not break deserialization.
        context: Option<serde_json::Value>,
    },
    Verify {
        cnf: Vec<Vec<i32>>,
        num_vars: usize,
        witness: Vec<u8>,
        /// Must match the seed used during Prove so the score constraint
        /// coefficients are reproduced exactly. Defaults to 0 if omitted.
        seed: Option<u64>,
    },
}

#[derive(Serialize, Deserialize)]
pub struct Response {
    pub success: bool,
    pub satisfiable: Option<bool>,
    pub witness: Option<Vec<u8>>,
    pub error: Option<String>,
}

// ── Error helper ──────────────────────────────────────────────────────────────

fn error_response(msg: impl Into<String>) -> Response {
    Response {
        success: false,
        satisfiable: None,
        witness: None,
        error: Some(msg.into()),
    }
}

// ── Input validation ──────────────────────────────────────────────────────────

/// Validate CNF and convert to the internal `[i32; 3]` clause type.
///
/// Rules enforced:
///   • num_vars ∈ [1, MAX_VARS]
///   • every clause has exactly 3 literals
///   • every literal is non-zero
///   • |literal| ∈ [1, num_vars]
fn validate_cnf(cnf: &[Vec<i32>], num_vars: usize) -> Result<Vec<Clause>, String> {
    if num_vars == 0 {
        return Err("num_vars must be greater than 0".into());
    }
    if num_vars > MAX_VARS {
        return Err(format!("num_vars {num_vars} exceeds maximum {MAX_VARS}"));
    }
    if cnf.len() > MAX_CLAUSES {
        return Err(format!(
            "clause count {} exceeds maximum {MAX_CLAUSES}",
            cnf.len()
        ));
    }

    let mut clauses = Vec::with_capacity(cnf.len());
    for (j, raw) in cnf.iter().enumerate() {
        if raw.len() != 3 {
            return Err(format!(
                "clause {j} must have exactly 3 literals, got {}",
                raw.len()
            ));
        }
        for &lit in raw {
            if lit == 0 {
                return Err(format!("clause {j} contains literal 0, which is invalid"));
            }
            let var = lit.unsigned_abs() as usize;
            if var > num_vars {
                return Err(format!(
                    "clause {j}: literal {lit} references variable {var} but num_vars is {num_vars}"
                ));
            }
        }
        clauses.push([raw[0], raw[1], raw[2]]);
    }
    Ok(clauses)
}

// ── Witness serialisation ─────────────────────────────────────────────────────
// Wire values (Goldilocks field elements) fit in 64 bits.
// Representation: little-endian u64 per element, tightly packed.

// Audit L-3 (#27): `witness_to_bytes` reads `f.into_bigint().0[0]` and silently
// truncates any higher limbs. That is correct for the single-limb Goldilocks
// Mont backend used today, but if `MontBackend<_, N>` is ever swapped for an
// `N > 1` field a witness round-trip would silently produce invalid bytes.
// Pin the assumption at compile time so that swap turns into a build break.
const _: () = assert!(
    <F as PrimeField>::MODULUS_BIT_SIZE <= 64,
    "witness_to_bytes / bytes_to_witness assume a single-limb (≤64-bit) field"
);

fn witness_to_bytes(w: &[F]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(w.len() * 8);
    for &f in w {
        let v: u64 = f.into_bigint().0[0];
        bytes.extend_from_slice(&v.to_le_bytes());
    }
    bytes
}

fn bytes_to_witness(bytes: &[u8], expected_elements: usize) -> Result<Vec<F>, String> {
    // Audit H-6 (#10): reject non-canonical encodings. F::from on a u64
    // value >= p silently reduces mod p, so two distinct byte strings can
    // map to the same field element. Any downstream byte-level tool
    // (transcript hash, cache key, signature over proof bytes) would then
    // disagree with what `verify` accepts. Enforce v < p at the parse
    // boundary so accepted byte strings and witness vectors are bijective.
    const GOLDILOCKS_P: u64 = 0xFFFFFFFF00000001;
    let expected_bytes = expected_elements * 8;
    if bytes.len() != expected_bytes {
        return Err(format!(
            "witness is {} bytes but expected {expected_bytes} ({expected_elements} field elements × 8 bytes)",
            bytes.len()
        ));
    }
    let mut result = Vec::with_capacity(expected_elements);
    for chunk in bytes.chunks_exact(8) {
        // chunks_exact guarantees exactly 8 bytes per chunk
        let arr: [u8; 8] = chunk.try_into().unwrap();
        let v = u64::from_le_bytes(arr);
        if v >= GOLDILOCKS_P {
            return Err(format!(
                "witness element {v} is non-canonical (>= field modulus {GOLDILOCKS_P})"
            ));
        }
        result.push(F::from(v));
    }
    Ok(result)
}

// ── Message dispatch ──────────────────────────────────────────────────────────

fn dispatch(req: Request) -> Response {
    match req {
        // ── Prove: run heuristic, return witness bytes if SAT ───────────────
        Request::Prove {
            cnf,
            num_vars,
            seed,
            ..
        } => {
            let clauses = match validate_cnf(&cnf, num_vars) {
                Ok(c) => c,
                Err(e) => return error_response(e),
            };
            let seed = seed.unwrap_or(0);

            match generate_witness(&clauses, num_vars, seed) {
                None => Response {
                    success: true,
                    satisfiable: Some(false),
                    witness: None,
                    error: None,
                },
                Some(w) => Response {
                    success: true,
                    satisfiable: Some(true),
                    witness: Some(witness_to_bytes(&w.to_witness_vec())),
                    error: None,
                },
            }
        }

        // ── Verify: reconstruct R1CS, check Hadamard product ────────────────
        Request::Verify {
            cnf,
            num_vars,
            witness,
            seed,
        } => {
            let clauses = match validate_cnf(&cnf, num_vars) {
                Ok(c) => c,
                Err(e) => return error_response(e),
            };
            let seed = seed.unwrap_or(0);

            let (sym, ent) = generate_fields(num_vars, seed);
            let r1cs = match build_sat_constraints(&clauses, num_vars, &sym, &ent) {
                Ok(r) => r,
                Err(e) => return error_response(e),
            };

            let expected_elements = r1cs.num_wires();
            let w = match bytes_to_witness(&witness, expected_elements) {
                Ok(v) => v,
                Err(e) => return error_response(e),
            };

            let valid = r1cs.verify(&w);
            Response {
                success: true,
                satisfiable: Some(valid),
                witness: None,
                error: None,
            }
        }
    }
}

// ── Wasm linear memory interface ──────────────────────────────────────────────

/// Allocate `size` bytes in Wasm linear memory; return pointer, or 0 on failure.
///
/// Edge cases (audit M-11, GH #22)
/// ────────────────────────────────
/// `alloc(0)` returns 0. This collapses two distinct conditions into the
/// same return value: a zero-byte request and a genuine allocator failure.
/// Hosts MUST NOT call `alloc(0)` and treat 0 as failure; instead they must
/// avoid zero-sized requests at the call site (the AO host always pairs a
/// non-empty payload with a non-zero `len`, so this is satisfied by
/// construction). The audit classified the resulting "is this address
/// allocated?" probe as NOT EXPLOITABLE in the AO model — there is no
/// secret address to leak to a same-instance attacker.
#[unsafe(no_mangle)]
pub extern "C" fn alloc(size: u32) -> u32 {
    if size == 0 {
        return 0;
    }
    let layout = match Layout::array::<u8>(size as usize) {
        Ok(l) => l,
        Err(_) => return 0,
    };
    let ptr = unsafe { std::alloc::alloc(layout) };
    if ptr.is_null() { 0 } else { ptr as u32 }
}

/// Free a buffer previously returned by `alloc` or `handle`.
///
/// Edge cases (audit M-11, GH #22)
/// ────────────────────────────────
/// `dealloc(0, _)` and `dealloc(_, 0)` are no-ops. Rationale:
///   • `(0, _)`: pointer 0 is reserved as the null/error sentinel.
///   • `(_, 0)`: a zero-size layout is not a valid `Layout::array::<u8>`
///     argument and cannot have come from this module's `alloc`.
/// A misbehaving host that calls `dealloc(p, 0)` with `p` non-zero leaks
/// the buffer; this is preferred over invoking the global allocator with a
/// mismatched layout (which is UB). The host contract requires `(ptr, len)`
/// to round-trip exactly the values returned by `alloc` / `handle`.
#[unsafe(no_mangle)]
pub extern "C" fn dealloc(ptr: u32, size: u32) {
    if ptr == 0 || size == 0 {
        return;
    }
    let layout = match Layout::array::<u8>(size as usize) {
        Ok(l) => l,
        Err(_) => return,
    };
    unsafe { std::alloc::dealloc(ptr as *mut u8, layout) }
}

/// AO entry point — called for every inbound message.
///
/// Memory contract
/// ───────────────
///   In:  UTF-8 JSON `Request` at linear memory address `ptr`, `len` bytes.
///        The host MUST have obtained `ptr` from this module's `alloc(len)`
///        export. `handle` CONSUMES the input buffer: do NOT call `dealloc`
///        on `(ptr, len)` after `handle` returns — `handle` already did.
///   Out: packed u64 → high 32 bits = pointer to UTF-8 JSON `Response`
///                      low 32 bits = byte length of that response.
///        The host MUST call `dealloc(response_ptr, response_len)` after
///        reading. On allocation failure `handle` returns 0.
///
/// Safety
/// ──────
/// Block 1 constructs a slice from host-provided (ptr, len) — valid because
/// AO guarantees the region is within Wasm linear memory and live for the call.
/// Block 2 frees that buffer; safe because the host obtained it via this
/// module's `alloc`, the slice has been fully consumed by `serde_json::
/// from_slice` (which copies into owned types), and no later code in this
/// function references `input`.
/// Block 3 copies the encoded response into a freshly allocated buffer —
/// valid because the buffer is exclusively owned until it is returned.
#[unsafe(no_mangle)]
pub extern "C" fn handle(ptr: u32, len: u32) -> u64 {
    if ptr == 0 {
        return pack_response(error_response("input pointer must be non-zero"));
    }
    if len as usize > MAX_INPUT_BYTES {
        // Free the input buffer even on rejection so the host doesn't have
        // to special-case error paths.
        dealloc(ptr, len);
        return pack_response(error_response(format!(
            "input is {len} bytes but maximum is {MAX_INPUT_BYTES}"
        )));
    }

    // ── 1. Parse JSON from inbound bytes (copies into owned types). ───────
    let response = {
        let input = unsafe { std::slice::from_raw_parts(ptr as *const u8, len as usize) };
        match serde_json::from_slice::<Request>(input) {
            Ok(req) => dispatch(req),
            Err(e) => error_response(format!("JSON decode failed: {e}")),
        }
    };

    // ── 2. Free the host-supplied input buffer. ───────────────────────────
    // The slice borrow above has ended; `serde_json::from_slice` copied any
    // bytes it kept. Dropping the input buffer now prevents a per-call leak
    // of `len` bytes of linear memory.
    dealloc(ptr, len);

    // ── 3. Pack the response into a freshly allocated buffer. ─────────────
    pack_response(response)
}

fn pack_response(response: Response) -> u64 {
    let response_bytes = match serde_json::to_vec(&response) {
        Ok(b) => b,
        Err(_) => br#"{"success":false,"error":"JSON encode failed"}"#.to_vec(),
    };

    // ── 3. Copy response into a fresh heap allocation ─────────────────────
    let resp_len = response_bytes.len();
    let layout = match Layout::array::<u8>(resp_len) {
        Ok(l) => l,
        Err(_) => return 0,
    };
    let resp_ptr = unsafe {
        let buf = std::alloc::alloc(layout);
        if buf.is_null() {
            return 0;
        }
        std::ptr::copy_nonoverlapping(response_bytes.as_ptr(), buf, resp_len);
        buf as u32
    };

    // ── 4. Pack (ptr || len) into the return u64 ──────────────────────────
    ((resp_ptr as u64) << 32) | (resp_len as u64)
}

pub fn process_json_request(input: &[u8]) -> Vec<u8> {
    let response = match serde_json::from_slice::<Request>(input) {
        Ok(req) => dispatch(req),
        Err(e) => error_response(format!("JSON decode failed: {e}")),
    };

    match serde_json::to_vec(&response) {
        Ok(b) => b,
        Err(_) => br#"{"success":false,"error":"JSON encode failed"}"#.to_vec(),
    }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn prove_json(cnf: &serde_json::Value, num_vars: usize, seed: Option<u64>) -> Response {
        let mut obj = serde_json::json!({
            "Action": "Prove",
            "cnf": cnf,
            "num_vars": num_vars
        });
        if let Some(s) = seed {
            obj["seed"] = serde_json::Value::from(s);
        }
        let req: Request = serde_json::from_value(obj).unwrap();
        dispatch(req)
    }

    /// (x1 ∨ x2 ∨ ¬x3) ∧ (¬x1 ∨ x2 ∨ x3) — satisfiable
    fn sat_cnf() -> serde_json::Value {
        serde_json::json!([[1, 2, -3], [-1, 2, 3]])
    }

    /// (x1 ∨ x1 ∨ x1) ∧ (¬x1 ∨ ¬x1 ∨ ¬x1) — unsatisfiable
    fn unsat_cnf() -> serde_json::Value {
        serde_json::json!([[1, 1, 1], [-1, -1, -1]])
    }

    #[test]
    fn prove_sat_returns_satisfiable_true() {
        let resp = prove_json(&sat_cnf(), 3, Some(42));
        assert!(resp.success, "success must be true");
        assert_eq!(resp.satisfiable, Some(true));
        assert!(resp.witness.is_some(), "SAT must return a witness");
        assert!(resp.error.is_none());
    }

    #[test]
    fn prove_unsat_returns_satisfiable_false() {
        let resp = prove_json(&unsat_cnf(), 1, Some(0));
        assert!(resp.success, "success must be true even for UNSAT");
        assert_eq!(resp.satisfiable, Some(false));
        assert!(resp.witness.is_none());
        assert!(resp.error.is_none());
    }

    #[test]
    fn invalid_cnf_zero_literal_returns_error() {
        let cnf = serde_json::json!([[0, 1, 2]]);
        let resp = prove_json(&cnf, 2, None);
        assert!(!resp.success);
        assert!(resp.error.is_some());
        assert!(resp.satisfiable.is_none());
    }

    #[test]
    fn oversized_num_vars_returns_error_not_panic() {
        let cnf = serde_json::json!([[1, 2, 3]]);
        let resp = prove_json(&cnf, MAX_VARS + 1, None);
        assert!(!resp.success);
        let err = resp.error.unwrap();
        assert!(err.contains("exceeds maximum"), "error was: {err}");
    }

    #[test]
    fn zero_num_vars_returns_error() {
        let cnf = serde_json::json!([[1, 1, 1]]);
        let resp = prove_json(&cnf, 0, None);
        assert!(!resp.success);
        assert!(resp.error.is_some());
    }

    #[test]
    fn wrong_clause_width_returns_error() {
        let cnf = serde_json::json!([[1, 2]]); // only 2 literals
        let resp = prove_json(&cnf, 2, None);
        assert!(!resp.success);
        assert!(resp.error.is_some());
    }

    #[test]
    fn literal_out_of_range_returns_error() {
        let bad = prove_json(&serde_json::json!([[1, 2, 99]]), 3, None); // var 99 > num_vars=3
        assert!(!bad.success);
    }

    #[test]
    fn oversized_clause_count_returns_error() {
        let cnf = serde_json::json!(vec![vec![1, 2, 3]; MAX_CLAUSES + 1]);
        let resp = prove_json(&cnf, 3, None);
        assert!(!resp.success);
        let err = resp.error.unwrap();
        assert!(err.contains("clause count"), "error was: {err}");
    }

    // ── M-11 / GH #22: alloc(0) and dealloc edge-case semantics ─────────────
    // The audit declared the "address probe" via alloc(0)/dealloc(0,_) NOT
    // EXPLOITABLE in the AO threat model. These tests pin the documented
    // behaviour so any future change (e.g. switching to a sentinel return)
    // is a deliberate, reviewed ABI break rather than an accidental one.

    #[test]
    fn alloc_zero_returns_null_sentinel() {
        // Documented contract: zero-size requests collapse to the null sentinel.
        assert_eq!(alloc(0), 0);
    }

    #[test]
    fn dealloc_with_zero_pointer_is_noop() {
        // Must not invoke the global allocator with ptr=0.
        dealloc(0, 16);
        dealloc(0, 0);
    }

    #[test]
    fn dealloc_with_zero_size_is_noop() {
        // Must not invoke the global allocator with size=0 (invalid Layout).
        // We deliberately pass a non-zero pointer that we never allocated;
        // the early return guarantees no UB.
        dealloc(0xDEAD_BEEF, 0);
    }

    // The positive-size alloc/dealloc round-trip relies on `usize == u32`
    // (Wasm32 linear memory) — on a 64-bit host the u32 pointer cast
    // truncates the real heap pointer and freeing it is UB. The non-trivial
    // path is exercised end-to-end by `cutover.mjs`'s WASM smoke test
    // (which loads the actual wasm32 artifact and round-trips a Prove
    // request through `alloc` / `handle` / `dealloc`).
    #[cfg(target_arch = "wasm32")]
    #[test]
    fn alloc_then_dealloc_roundtrip_succeeds() {
        let p = alloc(64);
        assert_ne!(p, 0, "alloc(64) must not return the null sentinel");
        dealloc(p, 64);
    }

    #[test]
    fn roundtrip_prove_then_verify() {
        let cnf = sat_cnf();
        let num_vars = 3usize;
        let seed = 42u64;

        // Prove
        let prove_resp = prove_json(&cnf, num_vars, Some(seed));
        assert!(prove_resp.success);
        assert_eq!(prove_resp.satisfiable, Some(true));
        let witness_bytes = prove_resp.witness.unwrap();

        // Verify
        let verify_req = Request::Verify {
            cnf: vec![vec![1, 2, -3], vec![-1, 2, 3]],
            num_vars,
            witness: witness_bytes,
            seed: Some(seed),
        };
        let verify_resp = dispatch(verify_req);
        assert!(verify_resp.success);
        assert_eq!(verify_resp.satisfiable, Some(true));
    }
}
