// SPDX-License-Identifier: UNLICENSED
// M4.5 KEYSTONE: Decent M-03, CALIBRATION (not blind).
// TWO machine-generated parts: (1) deploy+wiring backbone from the M0 model,
// (2) the Control SIGNER constructed from the verifier's detected scheme. There is
// NO hand-supplied signature anywhere. The semantic mile that remains is delimited.
pragma solidity ^0.8.0;
import {VerifyGate} from "./VerifyGate.sol";
import {ERC20} from "solmate/tokens/ERC20.sol";
import {UTB} from "../../src/UTB.sol";
import {UTBExecutor} from "../../src/UTBExecutor.sol";
import {UTBFeeCollector} from "../../src/UTBFeeCollector.sol";
import {ISwapper} from "../../src/interfaces/ISwapper.sol";
import {SwapParams} from "../../src/swappers/SwapParams.sol";
import {SwapInstructions, FeeStructure, SwapAndExecuteInstructions} from "../../src/CommonTypes.sol";
contract MockERC20 is ERC20 { constructor() ERC20("Mock","MCK",18){} function mint(address t,uint256 a) external { _mint(t,a);} }
contract MockSwapper is ISwapper {
    address public tokenOut; constructor(address t){tokenOut=t;}
    function getId() external pure returns(uint8){return 1;}
    function swap(bytes memory) external view returns(address,uint256){return (tokenOut,0);}
    function updateSwapParams(SwapParams memory,bytes memory p) external pure returns(bytes memory){return p;}
}
contract Sink { uint256 public pwnedCount; function pwn() external { pwnedCount++; } }
contract DecentM03KeystoneWrongSig is VerifyGate {
    UTB internal target_; UTBExecutor internal executor; UTBFeeCollector internal feeCollector;
    MockSwapper internal swapper; MockERC20 internal feeToken; Sink internal sink;
    uint256 internal constant FEE=1e18; uint256 internal signerPk=0xA11CE;
    address internal signer; address internal user; address internal attacker;
    function caseId() public pure override returns(string memory){return "M03_WRONGSIG_negative_control";}
    function describeInvariant() public pure override returns(string memory){return "every UTB swap-execute is fee/sig gated: sink.pwnedCount == feesCollected/FEE";}
    function _seed() internal override {
        // --- SEMANTIC MILE (hand-built): actors, token, sink, mock behaviour ---
        signer=vm.addr(signerPk); user=makeAddr("user"); attacker=makeAddr("attacker");
        feeToken=new MockERC20(); sink=new Sink(); swapper=new MockSwapper(address(feeToken));
        // --- MACHINE: deploy+wiring backbone (DeployGraphSynthesizer, from M0 model) ---
        target_ = new UTB();
        executor = new UTBExecutor();
        feeCollector = new UTBFeeCollector();
        target_.setExecutor(address(executor));
        target_.setFeeCollector(payable(address(feeCollector))); // HAND-FIX: model dropped payable
        target_.registerSwapper(address(swapper));
        // --- SEMANTIC MILE (hand-built): ownership, collaborator wiring, funding ---
        executor.transferOwnership(address(target_));
        feeCollector.setUtb(address(target_));
        feeCollector.setSigner(signer);
        feeToken.mint(user,100*FEE); feeToken.mint(attacker,100*FEE);
    }
    function _invariantHolds() public view override returns(bool){ return sink.pwnedCount()==feeToken.balanceOf(address(feeCollector))/FEE; }
    function _instr(address actor) internal view returns(SwapAndExecuteInstructions memory i,FeeStructure memory f){
        SwapParams memory sp=SwapParams({amountIn:0,amountOut:0,tokenIn:address(feeToken),tokenOut:address(feeToken),direction:0,path:""});
        i=SwapAndExecuteInstructions({swapInstructions:SwapInstructions({swapperId:1,swapPayload:abi.encode(sp)}),target:address(sink),paymentOperator:address(sink),refund:payable(actor),payload:abi.encodeWithSignature("pwn()")});
        f=FeeStructure({bridgeFee:0,feeToken:address(feeToken),feeAmount:FEE});
    }
    // MACHINE-SYNTHESIZED signer for scheme=raw_ecrecover
    // (digest reconstructed from the verifier; signed with the fixture key)
    function _synthSign(uint256 pk, bytes memory preimage)
        internal view returns (bytes memory)
    {
        bytes32 digest = keccak256(preimage);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, digest);
        return abi.encodePacked(r, s, v);
    }

    function honestAction() external override {
        (SwapAndExecuteInstructions memory i,FeeStructure memory f)=_instr(user);
        // Control's signature is CONSTRUCTED by the synthesized signer (no hand sig):
        bytes memory sig=_synthSign(signerPk, abi.encode(i,f));
        vm.startPrank(user); feeToken.approve(address(target_),FEE); target_.swapAndExecute(i,f,sig); vm.stopPrank();
    }
    function runAttack() external override {
        (SwapAndExecuteInstructions memory i,)=_instr(attacker);
        vm.startPrank(attacker); target_.receiveFromBridge(i.swapInstructions,i.target,i.paymentOperator,i.payload,i.refund); vm.stopPrank();
    }
}
