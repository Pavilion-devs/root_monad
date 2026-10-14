# Monad testnet adapter and deployment preparation

Updated 13 October 2026. The adapter is implemented and tested on a local EVM with
controlled finality responses. The public Monad testnet RPC also passed a read-only
connection check. **The registry is now deployed to Monad testnet**, with a
canonical finalized receipt in `results/monad-deployment.json`. The [live journey report](LIVE_MONAD_CHECK.md) records passing cross-app, correction,
conflict, revocation and migration checks, with one recovered interruption. See also
[wallet setup and execution](TESTNET_WALLET.md).

## Acceptance rule

The service and independent Python/TypeScript clients pin chain ID `10143` and the
registry address in their EIP-712 domain. Python's registry factory supports only
local Anvil (`31337`) and Monad testnet (`10143`); it rejects mainnet. Monad service
configuration requires HTTPS. Clients must supply their own trusted, pinned RPC.

For each verified read:

1. Read `eth_chainId` and `eth_getBlockByNumber("finalized")`. Reject an unavailable
   block or a timestamp more than 120 seconds old or 30 seconds in the future.
   The machine clock must be accurate. Never substitute `latest` or `safe`.
2. Read deployed code and the project head at that numbered finalized block.
   Verify the owner signature, project, manifests, content digests and current
   checkpoint. An explicit historical request may verify an older accepted head.
3. Read `acceptedAt(projectId, sequence)` at the same block. The contract records
   each sequence's acceptance block once. Fetch `Advanced` logs only for that
   single block, checking project, owner, sequence, predecessor and control digest.
4. Require a successful receipt containing that exact event, naming the pinned
   registry and matching its canonical block hash. Reread the receipt and the
   numbered authority block; inconsistent evidence fails closed.

The contract lookup is a new ABI/storage addition. An older local deployment must
be redeployed to use this adapter. Sequences cannot overwrite earlier acceptance
block entries. Private records and grants remain offchain.

This follows Monad's documented distinction between proposed, voted and finalized
blocks, including its warning that pre-finalization receipts can change:
[official JSON-RPC guidance](https://docs.monad.xyz/reference/json-rpc/overview).
A pinned RPC is still trusted. These checks are not a light client or an independent
consensus proof, and cannot detect a consistently dishonest RPC. The freshness
bound limits ordinary endpoint lag; it does not eliminate it.

## Pending writes and recovery

The signed transaction bytes and hash are encrypted and persisted before broadcast.
A receipt above the finalized tip remains pending, including a provisional failure
receipt. The adapter returns a terminal failure only for a stable, canonical failed
receipt below that tip. Retries submit identical bytes; they do not replace an
uncertain transaction or allocate a second approval.

Once finalized, the accepted intent also stores transaction hash, inclusion block
number/hash and the authority block used for verification. These saved observations
are audit evidence; fresh reads still query authority again.

Monad responses use `authorityMode: monad_testnet` and commit acknowledgements use
`confirmation: finalized_rpc_verified`. Local mode retains its explicit
`local_inclusion_only` label. `COMMIT_PENDING` and `FEE_LIMIT_EXCEEDED` are HTTP 503.

Initial service startup waits up to eight seconds for genesis acceptance, reopening
the same durable intent. If it still has not finalized, startup fails closed.
Restart with the same database and encryption key to continue recovery. Do not
replace the database to retry. RPC failures also prevent startup and verified reads.

Use one dedicated relayer per service and one unresolved local intent at a time.
Monad signing requires an explicit positive `registry.maxTransactionFeeWei` budget.
The current fixed gas limit is 300,000; signing is refused when that limit times the
observed gas price exceeds the budget. Funding, fee replacement and multi-writer
relayer coordination are not implemented. The owner and relayer have separate roles:
owner approval authorizes a checkpoint; the relayer pays to submit it.

## Evidence and checks

`tests/monad-finality.test.ts` runs an isolated Anvil instance with chain ID `10143`
and a controlled RPC proxy. A test-only URL override redirects HTTPS settings
to that proxy through the production persistent/batched Python transport; production settings do not allow this bypass. Merely using the Monad
chain ID does not turn the local test into a Monad deployment.

The scenario covers delayed genesis, a provisional failed receipt, pending recovery
across process restart, finalized acceptance, no duplicate update, independent
Python/TypeScript verification, stale current context, historical lookup, RPC
outage, wrong chain, old finalized tip, changing block/receipt and missing events.
Python unit tests additionally exercise terminal finalized failure, receipt/log
mismatch, empty contract, unavailable historical state, transport pins and fee caps.

Run `npm run typecheck` and `npm test`. Final validation passed type checking,
23 TypeScript test checks and 45 Python tests (68 total). Default tests do not
contact public RPCs or load real keys. Evidence is written to `results/monad-adapter.json`.

## Deployment preparation

From the project directory:

```sh
node_modules/.bin/tsx scripts/prepare-monad.ts
```

This separately opted-in script contacts the public testnet endpoint, checks chain
ID and fresh finalized state, compiles the contract and saves its ABI, creation
bytecode, hashes, compiler settings and unsigned transaction to
`results/monad-deployment-preparation.json`. It never signs or broadcasts.

Optionally pass `--deployer PUBLIC_ADDRESS` to include current nonce, balance,
estimated deployment gas and maximum fee at the observed gas price. The gas limit
has a 20% margin; these observations can expire and must be refreshed before signing.
`--rpc-url HTTPS_URL` and `--output FILE` override the endpoint and artifact path.
The artifact records only the endpoint origin to avoid copying provider URL tokens.

A dedicated local wallet has now been created and funded with Monad **testnet** MON.
See [wallet custody and commands](TESTNET_WALLET.md).
Only its public address is needed for preflight. Never use the repository's public
fixture keys for funding. Key custody/signing setup will be handled locally; private
keys should not be pasted into chat.

The durable deployment submission path now persists encrypted signed transaction
intents and confirms the resulting contract against finalized state. Its live
evidence is in `results/monad-deployment.json`; the unsigned artifact remains only
a preparation artifact. The live journey script tests conflicts, revocation and
migration against that pinned deployment. The memory HTTP server remains
loopback-only; the service itself has not been publicly hosted.

## Verification transport

The Python Monad adapter reuses a TLS connection and batches independent read
calls: chain ID with finalized tip, code with head at the selected block number,
and canonical inclusion block with a second receipt read. The initial receipt
read precedes its batch; the final authority-block hash check remains last.
The TypeScript verifier is unchanged and remains independently implemented.

No authority, permission or receipt result is cached across requests. A current
context still performs its final authority recheck before release. Batch results
are mapped by unique integer JSON-RPC IDs, including responses in arbitrary order;
missing, duplicate, unexpected or error responses fail the whole operation.
The transport limits batches to 16 read calls, responses to 4 MiB, and socket waits
to three seconds. These are per-exchange limits, not a whole-operation deadline.
Mutation calls cannot be batched. A failed exchange discards the connection and
returns `AUTHORITY_UNAVAILABLE`; there is no hidden transport retry. Durable commit
recovery remains responsible for resubmitting exactly the same signed bytes.
Endpoints that reject batches fail closed; no sequential fallback is implemented.

See [the latency comparison](MONAD_PERFORMANCE.md) for measured scope and limits.
