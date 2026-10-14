# Persistent memory with local registry authority

Implemented and tested on 12 October 2026. The encrypted Python memory service
can now use the Solidity registry as its reference for accepted revisions.
The browser demo still uses the signed-log mode. This implementation is limited
to local Anvil, chain ID 31337. A separate [Monad testnet adapter](MONAD_TESTNET.md)
now implements finalized-state verification; this report describes the local mode.

## Approval and recovery

1. An app proposes content. The owner reviews the exact prepared snapshot and
   signs a checkpoint under the deployed contract's EIP-712 domain.
2. The service validates the request, owner signature, base revision, prepared
   content and current app permissions. In one SQLite transaction it saves the
   encrypted commit intent, exact signed raw transaction, transaction hash and
   request receipt. Prepared content is already durably encrypted.
3. Only after that transaction commits does the service submit the raw transaction.
   A submission response alone is not acceptance. The service checks the registry
   and the matching `Advanced` event at a specific local block.
4. On startup and before signed requests, recovery checks pending intents. If the
   approval was accepted, it verifies the stored content and records acceptance.
   Otherwise it can resubmit the same raw bytes. It never creates a replacement
   transaction merely because a response was lost.
5. A different accepted update at that sequence is a conflict. An included failed
   transaction is a failure. A transaction without a conclusive outcome remains
   pending. No pending receipt is returned as a successful approval.

There is no atomic transaction spanning SQLite and the chain. The durable intent
bridges those two operations. Genesis registration uses the same path.
An approval may become visible between recovery's first check and a read; the
service can verify its staged signed envelope against the new registry head
without waiting for the local acceptance index to catch up.

A successful commit response includes the accepted event's transaction hash and
`confirmation: local_inclusion_only`. `COMMIT_PENDING` returns HTTP 503;
`TRANSACTION_FAILED` and `BASE_CONFLICT` return 409. Exact signed retries work
within the request's original deadline. After that deadline, make a fresh read to
check the accepted state; an expired HTTP request is not reusable. Recovery itself
continues to work after request expiry because the signed checkpoint and raw
transaction are retained separately.

## Reads and permission checks

Every request resolves the registry head and verifies the corresponding owner
signature and control document before checking permissions or returning a cached
reply. Missing authority produces an unavailable response. A newer head whose
signed envelope or private content is unavailable cannot fall back to an older
version presented as current. Loading an old database therefore cannot conceal
an already accepted newer revision.

The TypeScript registry verifier and Python client independently check the pinned
contract, owner, accepted event, content digests and completeness. Current reads
must match the head they observe. History must be explicitly requested with its
checkpoint digest; changing a response label to historical cannot bypass the
current-version check. Verification is point-in-time: a later approval can still
advance the head after a read completes.

The service checks private grants. The contract orders owner-approved commitments;
it cannot inspect private content or enforce offchain access itself. Revocation
blocks future guarded reads, including cached responses, but cannot recall copies
already held by an app. Proposal permission and expiry are checked when the
service durably accepts the owner's commit request, not by the contract at mining.

## Run and inspect

After the installation steps in [README.md](README.md):

```sh
npm run typecheck
npx tsx --test tests/memory-registry.test.ts
npm test
```

The integration test deploys a fresh registry on its own Anvil process, funds a
public disposable relayer with local test balance, starts the actual HTTP service,
and kills/restarts it at submission boundaries. Its fault injector is confined to
`tests/registry-crash-server.py`; there are no fault-injection API routes.

For an embedding launcher, `python/server.py` receives one startup JSON object on
stdin. Existing fields are `db`, the project `key`, `config`, optional `genesis`
and optional `port`. Registry mode additionally supplies:

- `config.domain`: name `PortableMemory`, version `0`, `chainId: 31337`, and the
  locally deployed `verifyingContract` address. This configuration is pinned in
  the encrypted database. Signed-log approvals cannot be reused under this domain.
- `registry: { rpcUrl: "http://127.0.0.1:<anvil-port>" }`.
- `relayerKey`: a dedicated local test account key, supplied through stdin and
  never stored as plaintext in the database or passed in command arguments.

`tests/memory-registry.test.ts` is the complete executable startup example.
The independent Python client's configuration also supplies `registry.rpcUrl`.
The TypeScript client uses `verifyRegistryContext` with its own pinned contract
connection, rather than trusting the service's verification label.

## Tested evidence

[Machine-readable results](results/memory-registry.json) cover:

- Process death after durable staging but before broadcast; restart submits once.
- Process death after chain acceptance but before local acknowledgment; restart
  recovers acceptance and retries do not add registry revisions.
- Independent Python and TypeScript verification of the same stored decisions.
- Rejection of stale client bundles, relabeled history and rolled-back storage.
- Two owner-reviewed candidates at one base; the second cannot overwrite the first.
- Permission withdrawal denying both fresh and previously cached reads.
- An unmined transaction reported pending; an independent competing approval wins
  and the pending local intent is classified as a conflict.
- Refusal to serve old current context when the winning signed envelope is missing.
- RPC outage returning unavailable instead of a cached, supposedly current result.

## Remaining boundaries

The local adapter described here trusts the local RPC. It checks a numbered block and that block's
hash during verification, but does not implement consensus verification, Monad's
finalized-block policy, or complete reorganization recovery. Event lookup scans
from genesis and is appropriate only for this small local experiment.

Use one dedicated relayer per service, with no unrelated transactions from that
account. The service permits one unresolved local intent at a time. Relayer nonce
replacement, fee adjustment, funding management and live deployment remain out
of scope. No real wallet was loaded or live transaction sent.

The service needs a usable current authority view at startup. If authority or the
current signed envelope is missing, startup refuses to serve. A verified current recovery archive can now supply a signed history to a new
provider. Incrementally synchronizing an arbitrary external winning envelope into
an existing service remains unfinished; it is never silently reconstructed from
unapproved local proposals.

Encrypted recovery and migration between isolated reference-provider instances
now pass; see [the recovery report](RECOVERY_MIGRATION.md). OS keychain custody,
independent-provider compatibility and real-wallet onboarding remain unfinished.
The [live model check](LIVE_MODEL_CHECK.md) now passes separately.
