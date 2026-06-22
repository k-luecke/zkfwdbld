// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

import {Test} from "forge-std/Test.sol";
import {console2} from "forge-std/console2.sol";

/// @title VerifyGate — the truth gate's on-chain harness.
///
/// This is the core of the Verification-Agent's "verify-or-discard" discipline.
/// A finding is NEVER trusted because "a test passed" or "a transaction did
/// something". It is trusted only when an *independently defined* invariant
/// predicate, which holds on honest state and survives honest use, is
/// specifically broken by the attack.
///
/// The PoC author overrides four hooks. They CANNOT decide the verdict — the
/// gate decides it, by evaluating `_invariantHolds()` across four phases:
///
///   1. BASELINE  invariant must hold on seeded honest state.
///                -> else REJECTED_MALFORMED_BASELINE (predicate is false at rest;
///                   any "break" it reports is meaningless).
///   2. CONTROL   a legitimate, fully-authorized action must PRESERVE it.
///                -> else REJECTED_MALFORMED_CONTROL (predicate is too brittle;
///                   it would "confirm" honest behaviour, so it launders nothing).
///   3. ATTACK    run the candidate exploit (caught: a revert is recorded, not fatal).
///   4. VERDICT   re-evaluate the SAME predicate:
///                - broken              -> CONFIRMED
///                - intact & reverted   -> REJECTED_ATTACK_REVERTED   (false hypothesis)
///                - intact & succeeded  -> REJECTED_INVARIANT_INTACT  (the wrong-reason
///                                         catch: the PoC changed on-chain state but did
///                                         NOT violate the stated invariant).
///
/// Soundness sketch: an always-true predicate can never produce CONFIRMED (the
/// attack phase can't break it). An always-false predicate is caught at BASELINE.
/// A predicate true-at-rest but broken by any state change is caught at CONTROL.
/// What survives all three guards and still breaks under attack is a genuine,
/// execution-proven invariant violation.
abstract contract VerifyGate is Test {
    // ---- author-supplied hooks -------------------------------------------

    /// Deploy + configure the target and seed honest starting state.
    function _seed() internal virtual;

    /// The invariant that MUST hold. Defined independently of the attack.
    /// This is the single source of truth for the verdict.
    function _invariantHolds() public view virtual returns (bool);

    /// A legitimate, fully-authorized interaction (the control). Must not break
    /// the invariant. Declared external so the gate can call it in try/catch.
    function honestAction() external virtual;

    /// The candidate exploit. Declared external so a revert is catchable.
    function runAttack() external virtual;

    // ---- metadata (for the report / human review) ------------------------
    function caseId() public view virtual returns (string memory);
    function describeInvariant() public view virtual returns (string memory);

    // ---- the gate (do not override) --------------------------------------

    string internal _verdict;

    function testGate() public {
        _seed();

        // Phase 1 — baseline
        if (!_invariantHolds()) return _emit("REJECTED_MALFORMED_BASELINE");

        // Phase 2 — control: honest use must preserve the invariant
        try this.honestAction() {
            if (!_invariantHolds()) return _emit("REJECTED_MALFORMED_CONTROL");
        } catch {
            return _emit("REJECTED_MALFORMED_CONTROL_REVERT");
        }

        // Phase 3 — attack (revert is recorded, not fatal)
        bool reverted;
        try this.runAttack() {} catch {
            reverted = true;
        }

        // Phase 4 — verdict, keyed strictly on the invariant predicate
        bool holds = _invariantHolds();
        if (!holds) return _emit("CONFIRMED");
        if (reverted) return _emit("REJECTED_ATTACK_REVERTED");
        return _emit("REJECTED_INVARIANT_INTACT");
    }

    function _emit(string memory v) internal {
        _verdict = v;
        // Machine-readable markers parsed by the Python harness.
        console2.log("VAGATE_CASE", caseId());
        console2.log("VAGATE_INVARIANT", describeInvariant());
        console2.log("VAGATE_VERDICT", v);
    }
}
