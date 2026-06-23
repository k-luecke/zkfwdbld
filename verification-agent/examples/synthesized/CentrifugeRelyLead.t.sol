// SPDX-License-Identifier: UNLICENSED
// Adjudicates the Seer STRUCTURAL lead: "executeScheduledRely bypasses auth".
// Deploys the REAL Root and runs the lead's hypothesis through the unchanged gate.
// NOTE: this _seed() was hand-derived for this demonstration; the GENERIC
// deploy-graph synthesizer is NOT built this session (see report). The verdict is
// what matters: a rejection proves the lead is a design-permissionless non-bug.
pragma solidity ^0.8.0;

import {VerifyGate} from "./VerifyGate.sol";
import {Root} from "../../src/Root.sol";

contract CentrifugeExecuteScheduledRelyLead is VerifyGate {
    Root internal root;
    address internal honestTarget;
    address internal attacker;

    function caseId() public pure override returns (string memory) {
        return "centrifuge_executeScheduledRely_auth_bypass__STRUCTURAL_LEAD";
    }
    function describeInvariant() public pure override returns (string memory) {
        // Hypothesis under test: the unguarded executor lets an unauthorized
        // address gain Root wardship. Invariant: the attacker is never a ward.
        return "no unauthorized wardship: root.wards(attacker) == 0";
    }

    function _seed() internal override {
        honestTarget = makeAddr("honestTarget");
        attacker = makeAddr("attacker");
        // Real deploy graph: Root only stores `escrow` as an address (unused on
        // this path), so a placeholder suffices. Deployer (this) becomes a ward.
        root = new Root(address(0xE5C0), 100);
    }

    function _invariantHolds() public view override returns (bool) {
        return root.wards(attacker) == 0;
    }

    // Control: the LEGITIMATE timelocked flow by a real ward (this contract).
    function honestAction() external override {
        root.scheduleRely(honestTarget);     // auth: ward-only
        vm.warp(block.timestamp + 101);       // wait out the delay
        root.executeScheduledRely(honestTarget); // permissionless execute of an AUTHORIZED schedule
    }

    // Attack: the lead's claim — attacker self-relies with NO prior schedule.
    function runAttack() external override {
        vm.prank(attacker);
        root.executeScheduledRely(attacker);  // reverts: "Root/target-not-scheduled"
    }
}
