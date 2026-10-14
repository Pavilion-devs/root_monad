# Local memory flow

12 October 2026. The prototype now supports encrypted persistence, signed HTTP
requests, owner review, accepted decisions, corrections, rejection, retraction,
and historical retrieval. The browser demo uses two application identities. An
independent Python client also reads and verifies the same accepted context in
the integration test.

This is a deterministic, sample-data prototype. No language model is connected.
The browser demo uses the owner-signed log with one local service as sequencer.
The service also supports local registry authority with durable commit intents
and crash recovery; see [the registry integration report](REGISTRY_SERVICE.md).

## Try it

From the project directory, run `npm run demo`. Open the printed local URL.

1. Send the initial planning suggestion for review. Current decisions stay empty.
2. Select Review change, inspect the text, and approve the decision.
3. Switch View through to Coding assistant. It retrieves the accepted version.
4. Choose Coding assistant as the author, then Correct the current decision.
5. Submit and approve the correction. Earlier versions retains the replaced text.
6. In the terminal running the demo, enter `r` to restart the service. Refresh the
   page; the current decision, history and owner evidence remain available.

The startup script creates an encrypted temporary database and keeps its project
key in the parent process's memory. Restarting the child service reuses that key.
Ending the demo discards the key and removes its temporary database. This verifies
service restart persistence, not recovery after losing the launcher or computer.
All signing identities in the demo are public disposable fixtures. Use sample
text only. The generic service accepts its key/configuration through stdin and
contains no built-in owner signing key.

## Implemented boundaries

| Area | Behavior |
| --- | --- |
| Private content | Objects, proposals, review bundles and cached replies are encrypted before SQLite receives them |
| Encryption | Fresh AES-256-GCM data key and nonce per object; wrapped data keys; project/type/object/epoch bound as associated data |
| Nonces | Random wrapping nonces checked against a uniqueness constraint; signed-request nonces retained transactionally through expiry |
| Request identity | Payload digest, project, service audience, current revision, deadline, recovered signer and current permission checked |
| Approval | Apps cannot prepare or commit; owner signature binds the prepared checkpoint to the exact control/snapshot digest |
| Review | Browser checks that the prepared snapshot matches the displayed proposal and leaves permissions/configuration unchanged |
| Corrections | A new immutable record supersedes the current one; stale or conflicting replacements cannot silently win |
| Retry | State changes and encrypted cached response commit in one SQLite transaction; an exact successful commit retry can be acknowledged after restart |
| Cache integrity | Cached replies authenticate signer and request fingerprint inside encryption; changing database pointers cannot substitute another response |
| Revocation | Current permissions are rechecked before cached replies; revoked applications lose future guarded access |
| Retrieval | Current reads omit historical record bodies; history is separately scoped; clients check completeness, digests and owner evidence |
| HTTP | Loopback binding, signed POSTs, size caps, Host/Origin checks, no CORS, no request-body logging |

Encryption uses the library's authenticated encryption primitive; the code does
not implement the cipher. SQLite transactions keep the local mutation and its
retry receipt together. These measures have the tested scope below, not a security
audit or a production guarantee.

Metadata such as object identifiers, object sizes, request signer/nonce and the
current control digest remains visible in SQLite. Project key custody, rotation,
recovery, retention and database rollback detection require further work. A copied
older database can contain valid old signatures: the baseline alone cannot prove
that it is the latest version.

## Verification

`npm run typecheck`, `npm run build:ui`, and `npm test` pass. The test runners report
21 TypeScript checks, including registry, migration and assistant integration, and
30 Python tests.

The new checks cover:

- Pending proposals do not appear as current decisions, and apps cannot approve.
- Python and TypeScript retrieve and verify the same accepted content over HTTP.
- Corrected text becomes current while the superseded text remains in history.
- Retraction removes current content; history still requires its separate permission.
- Two replacements of one current record cannot both be accepted in one batch.
- Missing sources, reused IDs, self-replacement and nonexistent targets fail.
- Invalid proposals roll back inserted objects and consume no request nonce.
- Proposal and commit retries survive reopening/restarting the service.
- Revocation rejects both cached and fresh requests.
- Wrong encryption keys, changed ciphertext and swapped cache pointers fail.
- Tampered content and omitted source evidence fail client verification.
- Database and WAL scans contain neither the sample memory text nor the input key.
- Cross-origin HTTP requests are denied.

The browser was manually exercised through proposal, approval, client switching,
correction and service restart. The resulting current record is 14 days, with
30 days shown as replaced. See [machine-readable results](results/memory-flow.json)
and [the captured screen](results/memory-demo.png).

## Deliberate prototype limits

The service supports one project per database, with at most 100 retained records,
sources, resolutions and submitted proposals in this slice. These smaller caps
keep full context/review responses manageable while pagination is unfinished.
Expired nonce rows are cleaned up, but orphaned encrypted objects and old response
objects do not yet have garbage collection. The demo serves loopback HTTP only.

OS credential-store integration, remote TLS deployment, real-wallet onboarding,
streaming responses and model summarization remain unfinished. Backend encrypted
recovery and migration between isolated reference-provider instances now pass;
see [the recovery report](RECOVERY_MIGRATION.md). Historical acceptance can be verified against the
owner signature, but there is no proof of live chain finality in this mode.

The demo UI intentionally keeps the first correction flow small: it corrects the
first current decision. The protocol supports multiple records, but choosing
among several decisions needs a fuller interface. The UI is an integration
example, not evidence of external adoption.

Local registry integration, interrupted-commit recovery and backend export/import
now pass. A fresh client continues after the original reference provider stops.
Reference assistant adapters now pass these deterministic checks; see
[their report](ASSISTANT_ADAPTERS.md). A bounded live Anthropic check now also passes; independent provider
compatibility and live Monad finality remain separate milestones.
