# Protected recovery and provider migration

Implemented and tested locally on 12 October 2026. This milestone changes only the
backend and protocol tooling. No browser interface was added or changed.

The test moves accepted project context from provider A into a newly encrypted
database at provider B, obtains an owner-signed service change, stops A, and
continues through fresh Python and TypeScript clients. Both providers are isolated
instances of our reference Python implementation. This is not yet an independent
third-party provider compatibility result or a live Monad deployment.

## What moves

The encrypted archive contains pinned project/owner/domain identity, the captured
head, contiguous signed checkpoint history, accepted snapshots, records, sources,
and signed proposal evidence. It retains corrections and pending proposals.
Imported pending suggestions never become owner decisions. The service change
makes those old proposals stale; they must be proposed against the new revision
before acceptance. The owner can still reject stale proposals explicitly.

The archive does not contain SQL, executable code, filesystem entries, HTTP retry
caches, relayer credentials or wallet signing keys. Storage locators are treated
as data, never fetched or interpreted as local paths during import. Original
project encryption keys are also unnecessary: the archive protects the logical
objects, and restore encrypts them under a newly generated project key.

This refines the initial design's proposal to carry the original project key in
an encrypted package. A logical archive avoids transferring an old provider's
storage key and lets a replacement storage implementation reconstruct its own
layout while retaining the same authority evidence.

## Key handling

Export generates a random 256-bit recovery key and encrypts the archive using
AES-GCM from the existing cryptography dependency. The recovery key is written to
a separate owner-selected file with mode 0600. It is never embedded in the archive
or printed by the tool. Keep that file separately from the archive: possession of
both grants access to the archived private context.

Restore generates a fresh 256-bit project key. Each restored object receives fresh
encryption, and `project-key.enc` protects the new project key under the supplied
recovery key. The capsule binds the pinned project, owner and domain. A service
launcher supplies the recovery key through stdin and loads the capsule; the tool
does not print the decrypted project key. The old provider's project key fails to
decrypt B's objects.

OS credential-store integration remains unfinished. The recovery-key file is an
explicit owner-held secret, not a claim of production key custody. Losing both
usable service key material and the recovery key loses access. A former provider
can retain old plaintext or keys; migration cannot erase its copies remotely.

## Migration sequence

1. **Export and freeze A.** Drain/resolve pending local commit intents, verify the
   registry head, capture a consistent SQLite transaction, and durably freeze new
   proposals and approvals. Reads remain available. Produce the encrypted archive
   and the separate recovery-key file. Export never overwrites an existing file.
2. **Restore B into staging.** The owner supplies independently trusted project,
   owner and contract-domain pins, the recovery key, a new service ID and a new
   storage descriptor. Verify the whole package and current registry head before
   publishing a new destination directory. Existing destinations are refused.
3. **Review the switch.** Prepare a new control revision that keeps the exact
   snapshot, changes the service/storage identifiers, and rebinds the existing
   grants to the new audience. Preparation alone does not advance the registry.
   B refuses application traffic until the owner approves this revision.
4. **Owner signs and commits.** Commit requires the owner's checkpoint signature;
   an application signature fails. Submission uses the existing durable-intent
   path. If the process stops after submission, reopening the database and
   retrying resolves the registry outcome without a second approval.
5. **Stop A and continue at B.** A cannot serve its old snapshot as current. B
   rejects requests addressed to A. Fresh clients verify B's current context
   directly against the registry, retrieve history, propose a correction and
   complete another owner approval with A offline.

The logical project identity and revision sequence persist across the move.
Application signing identities remain the same; the owner explicitly rebinds their
permissions to the new service. Local HTTP nonce caches and prepared drafts are
not transferred. Their old audience/base cannot authorize work at B.

Before committing the switch, `unfreeze` can resume A if its service binding still
matches the registry's current control. After the switch, an old provider cannot
unfreeze itself into current authority. Another accepted revision racing with
import causes a stale-export or unavailable-current-state failure; no restore
rolls the registry backward.

A backup must match the current accepted head to activate a restored service.
After later approvals, an old archive is insufficient to restore current state.
Keep a current backup; this implementation has no automatic backup scheduler or
remote fetch for missing newer objects. Failure while writing an export can leave
A frozen and a recovery-key file without an archive. Inspect the output paths,
then explicitly unfreeze/retry with fresh paths. Partial import staging never
replaces an active provider directory; abandoned staging after process death can
be removed by the owner once it is confirmed unused.

## Local administration interface

`python/admin.py` accepts one JSON request on stdin and returns JSON status or an
error code. It never accepts keys in command-line arguments or logs private
payloads. It is a local administrative tool, not an unauthenticated HTTP route.

All operations supply trusted `config` (`projectId`, `owner`, `domain`) and
`registry.rpcUrl`. This milestone uses only local Anvil on chain ID 31337.

| Operation | Additional input | Result |
| --- | --- | --- |
| `export` | Source `db`, `key`, dedicated local `relayerKey`, new `archive` path, separate new `recoveryKeyFile` path | Encrypted archive, separate recovery key, frozen source writes |
| `restore` | `archive`, `recoveryKey`, nonexistent destination `directory`, `binding` with new `serviceId` and `storage` | Staged `memory.sqlite` and `project-key.enc` |
| `prepare-migration` | Target `db`, `keyEnvelope`, `recoveryKey`, dedicated local `relayerKey` | Exact checkpoint/control/snapshot for owner review |
| `commit-migration` | Same target inputs plus `payload: {checkpoint, signature}` | Registry acknowledgment or unresolved/conflict error |
| `unfreeze` | Source key inputs | Resumes writes only while the source binding is still current |

Source key inputs can also use `keyEnvelope` plus `recoveryKey` instead of a raw
`key`. The HTTP server supports the same protected capsule inputs for startup.
Paths are chosen by the local owner/launcher; nothing in the archive chooses an
output path. Files are created exclusively with private permissions and synced;
restore validates in a temporary directory before publishing the result.

The complete executable example is `tests/migration.test.ts`. It creates all
identities, keys and paths for synthetic test data and cleans up only its own
resources. Run after installing dependencies:

```sh
npm run typecheck
npx tsx --test tests/migration.test.ts
.venv/bin/python -m unittest discover -s tests -p 'test_recovery.py'
npm test
```

## Verification and limits

The full suite passes: 20 TypeScript checks and 21 Python tests. The integration
[evidence](results/migration.json) includes the actual stopped-provider and fresh
client checks. Unit tests also decrypt, maliciously modify, and re-encrypt archives
to verify that encryption alone is not treated as authority: missing/changed
records, duplicate inventory, broken history, forged signatures, unsupported
labels/formats and path-like unexpected fields are rejected before publication.

Archives are capped at 16 MiB and inventories at 1,000 entries per collection;
existing service snapshot/proposal caps still apply. The tool cannot prove that a
source included every unapproved proposal it ever received. Owner-signed snapshots
and their referenced evidence must be complete; unsigned inbox completeness is
not a cryptographic guarantee.

Remaining work includes a separately implemented provider/importer, OS keychain
custody, live Monad finality, and assistant/model integration. There are no live
wallet transactions, model calls, UI changes or external deployment in this step.
