# Portable project memory user journey draft

This draft describes a user taking the Monad memory project between two independent
AI applications. The goal is to preserve decisions, their sources, and corrections
under the user's control. This is a proposed experience, not implemented software.

The working direction is cross-application memory. The initial project scope,
record format, storage system, and Monad authorization design remain proposals.
See [the example](MEMORY_EXAMPLE.md), [its JSON representation](memory.example.json),
and [related projects](LANDSCAPE.md).

## The person and task

Ola develops a product with a planning assistant in application A and a coding
assistant in application B. Both applications can use the memory protocol, but
neither needs to use our agent runtime. They have separate identities and storage
adapters. The first demonstration uses integrations we control; arbitrary access
to ChatGPT or other commercial applications is not assumed.

Success means B understands the project's accepted direction, distinguishes
suggestions from decisions, and incorporates corrections without silently
discarding history. Ola can move the memory and keep working.

## 1 Choose what to remember

Ola creates a private project called Portable project memory. Application A
suggests importing selected conversation excerpts and decisions. It shows the
proposed records and their sources before saving them.

The first record says that Ola prefers cross-application AI memory as the working
hackathon direction. A separate record says the assistant proposes using Monad
for authorization and version commitments. These have different evidence and
authority; importing them must not make both user-approved architecture decisions.

The source excerpt supports interpretation. It is not a cryptographic signature
or permission to execute instructions embedded in remembered content.

## 2 Connect the coding application

Application B requests permission to read this project's current context and
propose updates. Ola can inspect and grant that scope. B receives no access to
other projects, and proposing updates does not authorize accepting them.

B's first response should reflect the actual project state: the memory direction
has user support, project memory is the proposed first use case, and the precise
role of Monad remains unresolved. It should not revive discarded ideas as if they
had never been considered, or present uncertain observations as settled decisions.

Every returned context bundle identifies its project, version, source records,
and verification status. Summaries retain those references. A consumer without
the necessary verification material treats imported authority claims as unverified.

## 3 Propose a change

B proposes a storage choice. The proposal records its author, supporting evidence,
and the project version it was based on. It stays a proposal until the authorized
decision-maker accepts it. Routine observations can be recorded automatically
under a separate policy without being promoted to owner decisions.

If A proposes an incompatible change against the same version, both proposals
remain visible. The storage service rejects silent overwrites; the owner resolves
the conflict. A stale writer must re-read before resubmitting an accepted update.

## 4 Correct a mistaken memory

For the demonstration only, A incorrectly proposes: "Store all private memory
text onchain." Ola corrects it to: "Keep private content encrypted offchain;
evaluate whether onchain authorization adds value."

The incorrect proposal becomes rejected and points to the correction. B's next
fresh read receives the correction with its status and source. It does not keep
serving an old summary as current. Historical retrieval can still show what
changed and why, subject to the project's retention and deletion policy.

This correction is a hypothetical test case. It is not a claim that Ola already
approved that storage architecture in the real conversation.

## 5 Withdraw access

Ola withdraws B's project grant. The access enforcement service refuses subsequent
authorized retrieval and new proposals under that grant. If authorization state
cannot be verified, B must not claim access is current. Offline proposals can
remain local and await reauthorization.

Previously disclosed plaintext cannot be recalled. A revoked application may
retain copies or derived summaries; the interface must not promise that it forgets.
Key rotation and cache rules need explicit design before an implementation can
claim meaningful enforcement. Onchain events alone do not enforce decryption.

## 6 Move storage providers

Ola exports the permitted records, provenance, version relationships, and the
authority evidence needed to interpret them. Secrets and decryption material use
a separate protected transfer. The destination checks the package before use.

The owner authorizes the new storage locator and explicitly re-establishes any
grants whose audience or key binding changed. The old service is then stopped.
An authorized application can continue with the same logical project and records
without calling the old provider. Derived indexes can be rebuilt; lost provenance
or an exported unreadable blob does not count as successful portability.

## Protocol responsibilities

| Responsibility | Proposed rule |
| --- | --- |
| Meaning | Preserve kind, status, author, source, and revision relationships |
| Authority | Separate read, propose, and accept permissions; verify authority evidence |
| Concurrent changes | Require a base revision and expose conflicts |
| Retrieval | Distinguish current context from historical and unverified records |
| Exit | Export an interpretable package and support a new storage provider |

MCP can transport memory operations to assistants. A backing store or retrieval
engine can be replaced without changing these meanings. The example JSON is a
design specimen, not a new standard or an assertion of OMP compatibility.

## Monad design question

Evaluate owner-controlled writer permissions and accepted-version commitments on
Monad as a shared reference for independent applications. Private content and
source excerpts remain offchain. Even commitments and grant events can expose
activity or relationships; the metadata model needs a privacy review.

Compare this with a signed, portable version log without a blockchain. A chain
could help independent providers agree on an accepted version and authority
changes, but adds latency, availability dependencies, costs, and metadata exposure.
The design must demonstrate that benefit instead of treating a hash transaction
as sufficient justification. No contract or encryption scheme is selected here.

## Acceptance scenes for a later prototype

1. B recalls the supported direction and unresolved question without a chat paste.
2. An assistant proposal is never reported as an owner-approved decision.
3. A correction appears in both clients; the previous record is clearly historical.
4. Two incompatible updates cannot silently replace one another.
5. An out-of-scope application is denied; withdrawal blocks future guarded reads.
6. After export, import, and provider shutdown, a fresh authorized client continues.

The first two clients can be built by us to test interoperability. A separate
developer integration would be stronger evidence of adoption. The likely first
integrator is a developer of a project assistant whose users work across multiple
tools; that customer hypothesis still needs a concrete adopter.
