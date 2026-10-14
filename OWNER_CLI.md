# Owner commands

The `memory` command runs locally on this Mac against the existing hosted Monad
testnet project. It uses the owner key in the existing Keychain-protected vault.
The Claude MCP bridge never loads the owner vault or exposes these operations.
This separation is not an OS sandbox against other programs running as your user.
No additional model call, subscription or package installation is needed.

```sh
cd /Users/olathepavilion/Documents/portable-memory
./memory inbox
./memory apps
```

`inbox` displays full proposal IDs, the signed author's address, record kinds,
exact content and sources, replacements, retractions, and stale/pending/resolved
status. Resolutions come from an independently verified accepted snapshot.
A proposal's signature proves authorship, not that its content is true. The
provider can omit proposals; this command cannot prove inbox completeness.
Text is JSON-escaped to prevent terminal control sequences hiding review content.

`apps` lists current grants, permissions, expiry and locally known app names.
The original coding identity is shown as not granted; the planning and Claude
Code identities have their own grants. Names are local convenience labels;
the full address is the identity. Every read rechecks accepted chain state.

## Review and confirm

Copy a full proposal ID from the inbox:

```sh
./memory approve PROPOSAL_ID
./memory reject PROPOSAL_ID
```

Or copy an application address from `apps`:

```sh
./memory revoke APPLICATION_ADDRESS
```

Each command prepares one exact change and shows its effect, content/provenance,
current replacement targets or removed grant, previous and proposed revision,
expiry, and a `confirmation` value. Preparing writes a server-side review but
neither signs an acceptance nor changes accepted memory or permissions.

In an interactive terminal, paste the full confirmation value at the prompt to
sign that change. Press Enter to leave it as a preview. When input is not a
terminal, the command previews only. To confirm a saved preview explicitly:

```sh
./memory approve PROPOSAL_ID --confirm CHECKPOINT_FROM_PREVIEW
```

The same pattern works for `reject` and `revoke`. Confirmation must match the
saved action, target and checkpoint; it cannot silently generate a new review.
Only one local preview is retained. Preparing a different unsigned action replaces
that preview, so its old confirmation will no longer work. There is no `--yes`.
Reviews expire after five minutes. An expired unsigned preview can be prepared
again, with a new visible confirmation value.

Approval preserves each record's kind: accepting an observation does not turn it
into a decision. Rejection records a resolution while keeping current records
unchanged. A stale proposal can be rejected, but cannot be accepted; ask its author
to submit a fresh proposal against current memory. Revocation removes future
access through this service; it cannot erase copies an app already retrieved.
Owner review verifies that the service changed only the explicitly requested
proposal resolution or one application's grant before a checkpoint is signed.

## Interrupted approvals

```sh
./memory resume
```

A confirmed request is encrypted and saved locally before transmission. Resume
checks whether its checkpoint was accepted (including historical acceptance if a
later revision exists). If still valid and unaccepted, it resends the exact saved
request. It never creates a different approval. A response from the service is
not treated as success until the resulting state verifies against chain authority.

An unresolved confirmed request blocks preparation of another owner change.
Keep its journal. An expired signed request, conflicting revision or unavailable
history can require operator investigation; this version deliberately has no
force-reset command. Resolve the saved intent against finalized chain evidence
before replacing it. The CLI lock coordinates only CLI instances on this Mac;
other owner tools may still race, and predecessor checks reject their conflicts.

An `AUTHORITY_UNAVAILABLE` error means the chain could not be freshly verified;
`CONTENT_UNAVAILABLE` means the required content is unavailable. The earlier
server incorrectly reported both as `CONTENT_UNAVAILABLE`; the hosted connection
recovery fix distinguishes them. Idle RPC connections are replaced and interrupted
reads on reused connections get one reconnect, with no cached fallback. Retry a
read when the service is available. For any interrupted confirmed change, use
`resume` before starting another write. No cached memory is shown as current.

The journal lives under the existing owner's Application Support directory in
`hosted-memory/owner-cli/review.enc`, encrypted with the recovery key, mode 0600.
It contains private review data and the signed request; do not publish it.
Owner signing happens on this Mac, not in Claude or on the VPS. This command is
specific to the already configured testnet project; it is not general onboarding.

## First hands-on workflow

1. Read `./memory inbox` and review Claude's pending observation about a retention
   boundary test and the still-unspecified timestamp semantics.
2. Approve or reject it using the exact confirmation flow above.
3. Open the existing [Claude launcher](CLAUDE_CODE_INTEGRATION.md) and ask it to
   retrieve current memory and distinguish decisions from observations.

Implementation validation leaves that pending proposal untouched. Live confirmation
is intentionally left for the owner. Local tests exercise actual signed requests
against the reference service with disposable fixture keys, including lost-response
recovery, expired reviews, concurrency, revocation, and malicious response changes.
The historical sequence-1 backup remains stale; these commands do not refresh it.
