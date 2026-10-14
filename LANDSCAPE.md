# Related memory projects and reuse options

Research snapshot: 12 October 2026. Cross-application memory, scoped authorization,
temporal facts, and blockchain-backed memory all have existing implementations or
specifications. Our draft should build on these capabilities and test a narrower
claim: preserving user decision authority through correction, concurrent writes,
and provider migration. That combination is a hypothesis to compare, not established
novelty.

This review inspected primary documentation and selected source files. It did not
install these projects or reproduce their deployment, privacy, or performance claims.
No upstream code has been copied into this project.

## OpenMemory and Mem0

[OpenMemory](https://mem0.ai/openmemory) advertises MCP integration, project-scoped
context, typed memories, and access history. The inspected Mem0 plugin code has
project identity and scope handling and defaults to the hosted Mem0 API. Those
observations do not imply every Mem0 deployment uses that hosted path.

**Use:** study the integration experience and evaluate an existing engine for
capture and retrieval. Typed project memories and multi-tool delivery are baseline
features, not a differentiator we can claim.

Source: [plugin core](https://github.com/mem0ai/mem0/blob/b7ad69afda6b6ed030347c66d48a13e4de9dec08/integrations/agent-plugin-core/python/memory_core.py).
Repository license metadata: Apache-2.0. Hosted product features and the open-source
repository must be assessed separately when choosing components.

## Open Memory Protocol

[OMP](https://github.com/SMJAI/open-memory-protocol) publishes a portable record
schema and HTTP operations, including import/export. Its schema includes content,
type, source, namespace, timestamps, and metadata. The spec defines bearer auth
and import conflict strategies.

**Use:** compare our example with this schema before inventing a wire format.
Determine whether decision authority, revision relationships, and verified
acceptance can be represented as a documented extension. Metadata alone does not
guarantee another client will interpret those semantics.

Sources: [schema](https://github.com/SMJAI/open-memory-protocol/blob/2f91247accde20feab9718790aa8a06c077e32bd/spec/v1/memory.schema.json),
[specification](https://github.com/SMJAI/open-memory-protocol/blob/2f91247accde20feab9718790aa8a06c077e32bd/SPEC.md).
The repository's LICENSE is labelled Apache 2.0 but its text differs from the
standard full license; GitHub reports NOASSERTION. Clarify terms before code reuse.
It is a project-published specification; ecosystem-wide adoption is not established
by its name.

## User Owned Memory Protocol

[UOMP](https://github.com/0xaicrypto/uomp-core) describes local memory with scoped,
session-bound capability tokens and a guarding service. Its README explicitly
lists write staging/approval and onchain auditing as roadmap items; the documented
MVP defaults reject writes. The inspected SDK has read and write methods, which
does not by itself establish server-side write availability.

**Use:** learn from the requested-scope and authorization flow. Compare user-approved
updates against the pending write design. Do not adopt the README's deletion-proof
wording as proof that a recipient erased every plaintext copy.

Sources: [README](https://github.com/0xaicrypto/uomp-core/blob/93d1b1f804b5adb2a773325236c75fbba6403291/README.md),
[memory client](https://github.com/0xaicrypto/uomp-core/blob/93d1b1f804b5adb2a773325236c75fbba6403291/packages/sdk/src/memory.ts).
Repository license metadata: Apache-2.0.

## Lethe

[Lethe](https://github.com/vowctminibro/lethe) is the closest blockchain comparison:
its documented flow uses encrypted Walrus storage, Sui ownership/grants, a second
agent, and export. The inspected Move policy checks the vault namespace and whether
the caller is its owner or an authorized address before approving key access.

The README describes third-party agent access as near-term roadmap while using
its own companion agent to demonstrate the flow. Its claims of formal verification
were not reproduced in this review. Revocation concerns future guarded key access,
not erasure of plaintext already received.

**Use:** study separation of content storage and authorization. A port of the same
demonstration to Monad would not be a sufficient product contribution. Evaluate
provider migration and application-independent acceptance of changes separately.

Sources: [README](https://github.com/vowctminibro/lethe/blob/d61cdbd6e0d8aacaacf8542702772b1ee77f5a2b/README.md),
[key access policy](https://github.com/vowctminibro/lethe/blob/d61cdbd6e0d8aacaacf8542702772b1ee77f5a2b/contracts/memory/sources/memory_policy.move).
Repository license metadata: Apache-2.0. Sui/Seal code is not directly an EVM module.

## 0G Memory

[0G Memory](https://github.com/0gfoundation/0g-memory) builds on EverMemOS and
documents coding-assistant capture, structured retrieval, and encrypted persistence
on the 0G network. Its deployment includes several indexing services and a local
read cache.

**Use:** study capture adapters and restoration. Evaluate deployment and recovery
cost before choosing it as a base. Decentralized storage does not make all deployment
modes equivalent: its shared-server instructions state that the server stores each
user's wallet key. The uninstall instructions also describe loss of recovery when
a fresh installation creates a new stream and encryption key. Key recovery must
be part of our migration journey.

Source: [README](https://github.com/0gfoundation/0g-memory/blob/a03540cf1dbf91e7977e697ffba4a661ccab590c/README.md).
Repository license metadata: Apache-2.0. These are documentation findings, not a
security audit or an independent validation of persistence guarantees.

## Graphiti

[Graphiti](https://github.com/getzep/graphiti) describes temporal knowledge graphs,
provenance, validity windows, and superseding old facts while retaining history.

**Use:** consider an optional retrieval or historical-query backend. Correction
history and temporal facts are existing capabilities. Our authority model would
still need to distinguish an inferred fact update from an owner-approved decision.

Source: [README](https://github.com/getzep/graphiti/blob/0a3b1711b018e5590cf5c44a3ee3e67d6733ee13/README.md).
Repository license metadata: Apache-2.0.

## Design consequences

Keep the [user journey](JOURNEY.md) independent of any backend. First map the six
example records onto OMP, compare UOMP's authority model, and use Lethe as the
onchain baseline. A later prototype can use an established retrieval engine rather
than build a new vector database, graph store, or extraction framework.

The decisive interoperability test is whether a second implementation preserves
decision status, authority evidence, corrections, and conflicts after export/import.
If extensions lose those meanings, a successful JSON transfer is not enough.

Monad must justify its role against a signed version log. Shared ordering of
accepted updates and authority changes is a candidate benefit; privacy, key access,
availability, and the cost of integration remain design questions. Passkeys,
encryption, an MCP endpoint, or an onchain hash alone do not establish originality.

Before vendoring any selected code, inspect that component's actual license,
dependencies, and notices at the chosen revision and retain required attribution.
This research does not select a repository to fork.
