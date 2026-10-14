# Live Monad testnet check

Completed 13 October 2026. **Passed**, after one authority-unavailable interruption
and a resumed migration. Evidence: [deployment](results/monad-deployment.json) and
[live journey](results/monad-live.json). The registry is on Monad testnet; both memory
service instances ran locally on this Mac. This is a synthetic integration check,
not a production deployment, quality benchmark or external user study.

## Deployment

- Chain ID: 10143.
- Registry: `0x87207e30F12a9dF9ceF69657e4330f4D8fde6e67`.
- Deployment transaction: `0x0a5a473bb4564dc357524e41b0b397c2ef332ad8b9b7f710a6e14c54561c02de`.
- Receipt checked against canonical finalized state; deployed code hash pinned.
- Deployment gas charged: 970168.
- Deployment fee: 0.098957136 test MON.

A new dedicated wallet received 5 test MON from the official faucet after the user
completed its human-verification step. Its keys are encrypted outside the repository,
with the unlock key held in macOS Keychain. See [wallet custody](TESTNET_WALLET.md).

## What passed

1. Create a project on the deployed registry; independent Python and TypeScript
   clients verify its current memory.
2. Submit a planning-client proposal, approve it with the separate test-owner key,
   and read the accepted decision through the coding identity.
3. Propose a correction from 30 to 14 days. Keep the original current until
   approval, then share the corrected record. Reject a competing owner approval
   at the stale-base API check before sending another transaction. An actual EVM
   race is covered by local contract tests, not this live API rejection.
4. Revoke the coding identity. Reject both a fresh request and a previously cached
   read, using the finalized permission state.
5. Stop the source service, export an encrypted archive, restore a replacement
   instance with a fresh encryption key, and approve its locator/audience rebinding
   through the live registry. Reject the old audience and preserve revocation.
6. Read the corrected memory with fresh Python and TypeScript verification on the
   replacement, submit another proposal, and verify genesis history with Python.

The project finished at sequence 4. There were five accepted
project transactions: genesis, first decision, correction, revocation and migration.
All five receipts were rechecked against finalized state. Private record text was
stored locally, never placed in contract calldata. No model calls were made here.

## Interruption and recovery

The initial migration attempt returned `AUTHORITY_UNAVAILABLE`. Fresh verification
and encrypted export subsequently succeeded; the exact transient cause was not
isolated. We added a resumable migration phase that reuses the original project,
archive, target state and encrypted owner review. Earlier approvals were not replayed.
The report preserves the interruption rather than representing this as an
uninterrupted run. This demonstrates refusal of uncertain authority and explicit
recovery, not automatic high-availability failover.

## Measurements

These are single-run end-to-end observations over the public RPC from this Mac.
Successful API call samples include head lookup, request signing and service-side
verification. Independent client verification afterwards is not included. Commit
samples run from submission to verified acknowledgement. Migration administration,
failed requests, startup and the recovery pause are not included in this table.
They are **not measurements of Monad's block time or consensus finality latency**.

| Operation | Samples | Minimum seconds | Median seconds | Maximum seconds |
| --- | ---: | ---: | ---: | ---: |
| context | 5 | 12.355 | 14.372 | 23.042 |
| proposals | 3 | 9.710 | 9.836 | 10.261 |
| prepare | 4 | 11.490 | 11.659 | 11.852 |
| commit_to_verified_ack | 3 | 20.306 | 22.353 | 22.920 |
| history | 1 | 14.140 | 14.140 | 14.140 |

- Five project transactions: 0.153 test MON.
- Deployment plus project transactions: 0.251957136 test MON.
- Verified remaining relayer balance: 4.748042864 test MON.
- Fees are computed from each receipt's `gasUsed × effectiveGasPrice`.
- Total exercise elapsed time, including investigation and resumption: 595 seconds.

## Validation and next work

Type checking passed. Local validation passed 23 TypeScript checks and 41 Python
tests (64 total), including wallet encryption/tamper checks and deployment recovery
on a local EVM. Default tests never access this funded wallet or public RPC.

The latency work described by this baseline is now complete. Connection reuse and
batched independent reads retain the verification checks; a second full live
journey passed without interruption. See [the comparison](MONAD_PERFORMANCE.md)
for matched profiling, end-to-end timings and current validation. This document
preserves the original measurements and interruption history. Public service
hosting, third-party provider interoperability, independent wallet backup and
production key management remain open.
