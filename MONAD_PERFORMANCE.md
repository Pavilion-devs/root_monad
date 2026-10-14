# Monad verification latency

Measured on 13 October 2026 from this Mac against the public Monad testnet RPC.
This is a bounded comparison of our reference implementation. It is not a measure
of network consensus latency, a load test, or a production service-level guarantee.
The registry contract and verification policy were unchanged.

## Change and matched profile

Previously, each Python RPC call opened a fresh HTTPS connection. The Monad
adapter now reuses a connection and groups independent reads into JSON-RPC batches.
No verified result is cached between requests. Signatures, content digests, fresh
finalized tips, receipt membership and repeated canonical-block checks remain.

The [before profile](results/monad-profile-before.json) and
[after profile](results/monad-profile-after.json) each contain three reads of the
same existing migrated project and checkpoint. Each sample runs the service's
head lookup plus a signed context request directly in Python. HTTP loopback
handling and independent client verification are outside these timings; service
initialization is excluded. The optimized samples use a warmed connection.
The profile performs no chain writes, although signed-request bookkeeping still
writes to the local encrypted database.

| Measure | Before | After |
| --- | ---: | ---: |
| Median seconds, three reads each | 15.651 | 3.205 |
| Minimum seconds | 14.720 | 3.003 |
| Maximum seconds | 18.966 | 3.243 |
| Logical RPC calls per read | 30 | 30 |
| HTTP requests per read | 30 | 21 |

The observed median dropped 79.5%, or about 4.9 times faster. More than 99% of the
original measured time was inside RPC calls. The new transport opened zero new
connections during the three warmed samples and reported zero exchange errors.
Connection reuse and batching were applied together; this experiment does not
isolate the contribution of each change. Network conditions may differ between
samples, and three reads do not establish tail latency.

## Verification and failure behavior

- Chain identity and finalized-tip reads share one batch. Code and head reads
  share a second batch pinned to that tip's block number.
- The initial receipt read remains separate. Its canonical block and second
  receipt read share a batch. The authority-block hash recheck remains last.
- Responses are matched to unique integer IDs, regardless of response order.
  Partial, duplicate, unexpected, malformed or error results fail the check.
- A failed exchange discards the connection and does not replay a transaction.
  The initial version reconnected only on the next explicit operation. The
  13 October hosted fix also evicts idle connections and permits one reconnect
  for an interrupted read on a reused socket; see [hosting](HOSTING.md). Existing
  durable transaction recovery remains responsible for exact-byte resubmission
  after uncertain acknowledgement.
- The adapter does not fall back to `latest`, return an older cached authority
  result, or silently fall back to sequential requests if an endpoint rejects batches.

Type checking passes. The full local suite passes 23 TypeScript checks and
45 Python tests (68 total). New tests cover connection reuse, out-of-order batch
mapping, invalid batch responses and uncertain broadcast without automatic replay.
The controlled finality integration now runs the service through the actual
batched transport and rejects wrong-chain, unavailable/stale finalized state,
changed canonical blocks, changing receipts and missing events. Its expanded
failure assertions also passed in a separate focused rerun. These are local tests;
the public-chain evidence is recorded separately below.

## Full live HTTP journey

The [optimized live run](results/monad-live-optimized.json) passed all 12 checks,
without interruption or resumption. It created a fresh synthetic project using
the same deployed registry and completed in 157 seconds. Both memory services
ran locally; finalized authority reads and transactions used public Monad testnet.
The original [baseline journey](results/monad-live.json) is preserved unchanged.

Timings below include actual HTTP head lookup, request signing and service-side
verification. Commit timing begins at signed submission and ends at verified
acknowledgement. Independent Python/TypeScript verification afterwards, migration
administration, rejected requests and initialization are outside these samples.
The full journey still performs independent verification, but does not include
its cost in API timing. The two journeys use different synthetic projects, with
the same operation sequence; they are not repeated reads of one unchanged head.

| Operation | Samples per run | Baseline median seconds | New median seconds | New range seconds |
| --- | ---: | ---: | ---: | ---: |
| context | 5 | 14.372 | 4.610 | 3.861–7.288 |
| proposals | 3 | 9.836 | 3.910 | 3.392–4.081 |
| prepare | 4 | 11.659 | 3.196 | 2.331–3.477 |
| commit_to_verified_ack | 3 | 22.353 | 5.655 | 5.071–11.397 |
| history | 1 | 14.140 | 3.201 | 3.201–3.201 |

Observed median API context retrieval improved from 14.372 to 4.610 seconds
(67.9% lower); verified commit acknowledgement improved from 22.353 to 5.655
seconds (74.7% lower). The matched profile above isolates a narrower service path;
its 3.205-second result should not be substituted for the full HTTP median.
These samples still show variable public-RPC latency and are not guarantees.

The live run verified cross-app reads, pending corrections staying unapproved,
shared accepted corrections, stale-base approval rejection, revocation of fresh
and cached reads, source shutdown, encrypted migration, audience rebinding,
continued reads/proposals, preserved revocation and historical access. As in the
baseline, the competing approval was rejected at the API before another chain
transaction; the actual EVM race is covered by local tests.

Five accepted transactions ended at sequence 4; all receipts were checked against
finalized state. This additional journey cost 0.153 test MON, computed from receipt
gas usage and effective gas price. No contract redeployment or model calls were
needed. Test services were stopped after completion.

The next milestone is a hosted memory service with protected configuration,
restart recovery and an external client exercise. Independent provider
interoperability and production key custody remain open. The current setup still
trusts its configured RPC and uses two instances of the same reference provider.

## Reproduce without replacing evidence

For another onchain read-only profile of the original migrated project:

```sh
.venv/bin/python scripts/profile-monad.py --live --output results/monad-profile-new.json
```

This requires this Mac's protected test wallet and original exercise state. The
command profiles the current implementation; the saved before profile was captured
before the transport change. Existing output files are refused.

For a fresh full synthetic journey, including five testnet transactions:

```sh
.venv/bin/python scripts/monad-exercise.py --live --output results/monad-live-new.json
```

Choose an unused output path. See [custody and resumption](TESTNET_WALLET.md).
