// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

// Offline fixture for the verification-surface tagger. It is NOT a real
// protocol and is intentionally minimal. Each function below sits on one of the
// five priority surfaces the agent specializes in, plus a couple of decoys that
// must NOT be tagged (generic accounting / view helpers).

contract SurfaceSampler {
    address public owner;
    mapping(bytes32 => bool) public consumedMessages;
    mapping(address => uint256) public stake;
    bytes32 public stateRoot;

    // --- signature / proof verification surface ---
    function claimWithSig(bytes32 digest, uint8 v, bytes32 r, bytes32 s) external {
        address signer = ecrecover(digest, v, r, s);
        require(signer == owner, "bad sig");
    }

    function verifyProof(uint256[8] calldata proof, uint256[2] calldata input)
        external
        view
        returns (bool)
    {
        // pretend groth16 verifier
        return proof[0] != 0 && input[0] != 0;
    }

    // --- merkle / state-proof surface ---
    function proveStorage(bytes32 leaf, bytes32[] calldata merkleProof) external view returns (bool) {
        bytes32 computed = leaf;
        for (uint256 i = 0; i < merkleProof.length; i++) {
            computed = keccak256(abi.encodePacked(computed, merkleProof[i]));
        }
        return computed == stateRoot;
    }

    // --- bridge inbound handler surface ---
    function relayMessage(uint256 nonce, address target, bytes calldata message) external {
        bytes32 id = keccak256(abi.encode(nonce, target, message));
        require(!consumedMessages[id], "replayed");
        consumedMessages[id] = true;
        (bool ok, ) = target.call(message);
        require(ok, "call failed");
    }

    // --- cross-domain auth surface (modifier-expressed) ---
    modifier onlyCrossDomain() {
        require(msg.sender == address(this), "not messenger");
        _;
    }

    function setStateRoot(bytes32 newRoot) external onlyCrossDomain {
        stateRoot = newRoot;
    }

    // --- slashing / AVS surface ---
    function slashOperator(address operator, uint256 amount) external {
        require(msg.sender == owner, "not owner");
        stake[operator] -= amount;
    }

    // --- decoys: generic accounting / views that must NOT be tagged ---
    function contribute() external payable {
        stake[msg.sender] += msg.value;
    }

    function currentOwner() external view returns (address) {
        return owner;
    }
}
