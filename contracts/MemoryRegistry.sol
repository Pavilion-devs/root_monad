// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

/// Experimental ordering registry. Private content and grants are enforced offchain.
contract MemoryRegistry is EIP712 {
    struct Checkpoint {
        bytes32 projectId;
        uint256 sequence;
        bytes32 previousDigest;
        bytes32 controlDigest;
        uint256 deadline;
    }
    struct Head { address owner; uint256 sequence; bytes32 digest; }
    mapping(bytes32 => Head) public heads;
    // Sequence numbers are unique per project; clients can fetch one event block.
    mapping(bytes32 => mapping(uint256 => uint256)) public acceptedAt;
    bytes32 private constant CHECKPOINT_TYPEHASH = keccak256(
        "Checkpoint(bytes32 projectId,uint256 sequence,bytes32 previousDigest,bytes32 controlDigest,uint256 deadline)"
    );
    error InvalidGenesis();
    error UnknownProject();
    error AlreadyExists();
    error Expired();
    error WrongSigner();
    error BaseConflict();
    error InvalidDigest();
    event Advanced(bytes32 indexed projectId, address indexed owner, uint256 sequence,
        bytes32 previousDigest, bytes32 controlDigest);

    constructor() EIP712("PortableMemory", "0") {}

    function projectIdFor(address owner, bytes32 creationNonce) public pure returns (bytes32) {
        return keccak256(abi.encode(owner, creationNonce));
    }

    function create(address owner, bytes32 creationNonce, Checkpoint calldata cp,
        bytes calldata signature) external {
        if (owner == address(0) || cp.projectId != projectIdFor(owner, creationNonce) ||
            cp.sequence != 0 || cp.previousDigest != bytes32(0)) revert InvalidGenesis();
        if (heads[cp.projectId].owner != address(0)) revert AlreadyExists();
        _verify(owner, cp, signature);
        heads[cp.projectId] = Head(owner, 0, cp.controlDigest);
        acceptedAt[cp.projectId][0] = block.number;
        emit Advanced(cp.projectId, owner, 0, bytes32(0), cp.controlDigest);
    }

    function advance(Checkpoint calldata cp, bytes calldata signature) external {
        Head storage head = heads[cp.projectId];
        if (head.owner == address(0)) revert UnknownProject();
        if (cp.previousDigest != head.digest || cp.sequence != head.sequence + 1) revert BaseConflict();
        _verify(head.owner, cp, signature);
        head.sequence = cp.sequence;
        head.digest = cp.controlDigest;
        acceptedAt[cp.projectId][cp.sequence] = block.number;
        emit Advanced(cp.projectId, head.owner, cp.sequence, cp.previousDigest, cp.controlDigest);
    }

    function _verify(address owner, Checkpoint calldata cp, bytes calldata signature) private view {
        if (block.timestamp > cp.deadline) revert Expired();
        if (cp.controlDigest == bytes32(0) || cp.controlDigest == cp.previousDigest) revert InvalidDigest();
        bytes32 hash = _hashTypedDataV4(keccak256(abi.encode(CHECKPOINT_TYPEHASH,
            cp.projectId, cp.sequence, cp.previousDigest, cp.controlDigest, cp.deadline)));
        if (ECDSA.recover(hash, signature) != owner) revert WrongSigner();
    }
}
