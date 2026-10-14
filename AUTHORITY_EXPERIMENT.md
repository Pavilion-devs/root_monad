# Local authority experiment

12 October 2026. The local experiment demonstrates the proposed shared-ordering
benefit: two signed-log replicas can disagree about an accepted successor, while
the registry accepts one successor and makes that choice queryable by another
client. This supports continuing the local memory prototype. It does not yet
justify a Monad-specific performance claim or a production deployment.

## What was built and exercised

| Experiment | Observed result | Evidence |
| --- | --- | --- |
| Independent Python and TypeScript encoding/signatures | Same canonical control bytes, project ID and digests; each verifies the other's checkpoint and request signatures | [Cross-language results](results/cross-language.json) |
| Two signed-log replicas | Both accept valid but different owner-signed successors from the same predecessor; local conflict detection does not choose a global winner | [Signed-log results](results/signed-log.json) |
| Local EVM registry | First successor accepted; competing successor and raw replay rejected; another RPC client sees the selected head | [Registry results](results/authority-comparison.json) |
| Owner/domain checks | Wrong owner, changed content, wrong chain, wrong contract, baseline-domain signatures, expired checkpoints and skipped sequence rejected | Registry tests |
| Request permissions | Wrong scope/audience and requests after confirmed revocation denied; identical retry returns cached result without rerunning action | Protocol and registry tests |
| Storage failure | Missing or mismatched control content fails rather than returning the old context as current | Registry tests |
| Unknown acknowledgement | Repeating an already committed checkpoint is recognized without another transaction | Registry tests |

The EVM harness uses Anvil on chain 31337 with the Cancun hardfork, solc 0.8.36,
and OpenZeppelin Contracts 5.6.1. A Python-generated owner signature was accepted
by the contract. Contract deployment and transactions used local throwaway accounts.
No live Monad transaction, model call, real credential or wallet was involved.

The first successful local measurement recorded 79,834 gas for creation and
61,848 gas for one update. These are single local EVM samples, not Monad fees or
throughput measurements. Signature bytes can slightly change transaction gas;
reruns may differ. The JSON report contains the latest run's values.

Validation: TypeScript type checking passed, the Node test runner reported 17
passing checks (including the registry suite), and all 6 Python tests passed.

## Decision from this experiment

Retain the registry as the candidate shared authority adapter. It solves a specific
coordination question: which owner-authorized checkpoint should independent clients
use when a provider offers an old history or two owner devices sign competing
successors? It does not determine whether the content is true or useful.

A signed log with one trusted sequencer also orders updates. If users are happy
with one permanently trusted memory service, the blockchain may add little.
The product hypothesis is that a replaceable provider and independent verifiers
are valuable enough to warrant a public shared reference. That hypothesis still
needs a working user journey and external integration feedback.

These ordering properties are portable across compatible EVM chains. Monad's
specific case must be established through actual integration, experience and
measurements. We have not proven that this product uniquely needs Monad.

## Confirmation rule for the future Monad adapter

Monad documents `latest` as proposed state and `finalized` as finalized state;
a receipt can refer to an unfinalized block. The live adapter must therefore use
a finality check rather than treating receipt arrival as acceptance.
[Monad JSON-RPC overview](https://docs.monad.xyz/reference/json-rpc/overview)

The selected implementation rule for the next adapter is:

1. Persist the transaction hash before polling. A missing receipt leaves the
   operation pending or unknown; it does not prove submission failed.
2. Fetch the receipt and a finalized block. Require successful execution and a
   receipt block no higher than the finalized height.
3. Fetch the canonical receipt block and compare its hash with the receipt's
   block hash. Re-fetch the receipt if it changes. A mismatch remains unconfirmed.
4. Verify the expected registry address and update event. Read current registry
   state at an explicitly selected finalized block. A later head may already
   supersede this update; report the update's success separately from current state.
5. On RPC errors or unavailable historical state, remain unverified. Do not fall
   back to `latest` and label it final. Fresh authorization reads also pin a
   finalized block and report that block's number/hash.

This rule is specified, not implemented or tested against a live Monad RPC.
The existing `RegistryAdapter` deliberately confirms local Anvil inclusion only.
Trusted RPC accuracy remains a V0 assumption; these checks are not a light client.

## Limits and next implementation

The authority schemas cover control documents and authenticated requests only.
Snapshot/record/source validation and the human review flow remain to be built.
The contract commits an opaque digest: it cannot inspect private grants, prevent
bad owner-approved memory, decrypt content, or restore missing objects.

The permission gate verifies requests against a control document that the caller
has already checked against the registry. Its nonce cache is in-memory and its
actions are synchronous test callbacks. A real service needs transactional,
persistent replay handling, bounded caches, crash recovery, and an authenticated
HTTP boundary. No restart-safe or concurrent-disclosure guarantee is claimed here.

Next build one local path: create project context, propose a change, review and
accept it, then retrieve it from a second client. Add full memory schemas and
transition fixtures first; then encrypted storage and persistent service state.
Keep the live Monad deployment and its finality/fee measurements for the separate
integration stage. The technical ordering check passed; product value remains
conditional on the actual user experience.


The separate [memory slice](MEMORY_SLICE.md) now implements full memory schemas,
encrypted persistence, a signed HTTP service and owner review in signed-log mode.
The limitations above describe this authority experiment; the newer report tracks
the current memory implementation.
