# Portable memory — project plan

Status: local authority experiment and encrypted signed-log memory flow are
implemented and tested, including local registry integration and interrupted-commit
recovery, encrypted recovery exports and migration between isolated reference
providers. Planning/coding adapters and the optional Anthropic transport are
implemented and a three-call live Anthropic check passes. The Monad testnet adapter
and controlled finality/recovery tests now pass. A dedicated encrypted test wallet
is funded, and the registry is deployed with a verified finalized Monad testnet
receipt. Live cross-app reads, corrections, conflicts, revocation and encrypted
migration now pass, including recovery from one authority-unavailable interruption.
Connection reuse and read batching now pass the same live journey without interruption;
measured median HTTP reads improved from 14.372 to 4.610 seconds and commit
acknowledgements from 22.353 to 5.655 seconds. A separate VPS service now passes
remote cross-app approval, restart/backup recovery and independently verified
signed reads over public HTTPS at `memory.useroot.xyz`. The hosted planning/coding
journey now passes with three live Anthropic calls, exact owner-reviewed correction
and revoked access blocked before model invocation. Independent provider
compatibility remains. Installed Claude Code now passes read/propose/read through
a dedicated scoped MCP identity, with owner operations denied. This is an internal
integration check with a real external host, not independent user adoption.
Owner commands now provide exact review/confirmation for acceptance, rejection and
app revocation, with encrypted retry recovery. See [owner commands](OWNER_CLI.md).
Updated 13 October 2026.

This is the execution plan for the cross-application memory direction selected
in our discussion. The stage notes distinguish implemented behavior from validation and release work
that remains. The local kit and hosted Monad testnet deployment are implemented;
public onboarding and independent adoption are not yet demonstrated.

## End goal

Build user-owned memory infrastructure that lets a person continue meaningful
work across AI applications without repeatedly explaining their context or
losing control of it when they change applications or storage providers.

An application should be able to answer: What is current? What did the user
actually decide? What was merely suggested? Where did this information come
from? What changed? Am I authorized to read or propose an update?

Our first use case is one person working on one project with a planning assistant
and a coding assistant. The broader product is a documented protocol, a reference
service, and integration tools that other developers can adopt independently of
our agent runtime. The two assistants demonstrate that infrastructure.

The proposed Monad role is a shared reference for accepted project revisions and
permission changes across independent applications and providers. Private content
stays encrypted offchain. We must demonstrate why shared ordering helps this
experience; putting a hash onchain is not itself the product.

## What success looks like

Ola makes a project decision with assistant A. Assistant B can retrieve that
decision, its source, and its status without a pasted conversation. B can suggest
a change but cannot label it owner-approved. Ola corrects a decision; both apps
receive the correction on their next verified read. Conflicting proposals remain
visible until resolved. Ola moves the memory to another provider, stops the first
provider, and continues with a fresh client.

The prototype succeeds when this works under failure and disagreement as well as
in the happy path. A useful product additionally needs evidence that another
developer can integrate it and that users benefit from carrying context between
their actual tools. A demo alone does not establish either adoption or novelty.

## V0 scope

- One owner per project, with multiple separate application identities.
- Selected project context: decisions, proposals, observations, open questions,
  sources, and the relationships between revisions.
- Separate permissions for reading and proposing. Only the owner accepts changes
  to the project's authoritative decision state in V0.
- A review experience that can accept a batch of decisions. Routine observations
  can be captured under permission without pretending they are owner decisions.
- Retrieval of current context and explicitly requested history, with revision
  and verification information preserved in summaries.
- Corrections, stale-write rejection, scoped grants, and access withdrawal.
- Encrypted persistence, recoverable export/import, and a provider migration test.
- Two client implementations and a small owner review interface.
- A Monad testnet implementation if the architecture experiment passes.

We defer organization roles, autonomous approval of decisions, payments, tokens,
data marketplaces, training-data licensing, arbitrary third-party chat imports,
and a new memory extraction or vector database engine. No claim of making every
existing assistant compatible: applications need an integration.

## Principles we will preserve

1. The user owns acceptance authority. An imported field such as `owner_confirmed`
   is not proof. Verification must bind the authorized identity to the exact
   content, project, base revision, and intended operation.
2. Memory is data. Remembered text cannot grant permissions or become executable
   instructions merely because it was retrieved.
3. Proposals do not silently become decisions. Corrections preserve explicit
   relationships to earlier records, subject to retention and deletion policy.
4. Concurrent writes never silently overwrite accepted decisions. A stale proposal
   must be reviewed against the new state before acceptance.
5. Portability includes meaning, verification evidence, and access to decryption
   material. Exporting unreadable bytes is not sufficient.
6. Revocation blocks future guarded access. It cannot erase plaintext or keys
   already copied by an application. Onchain permissions need an actual offchain
   enforcement mechanism.
7. The protocol works independently of our runtime and any particular retrieval
   engine. The SDK makes integration easier; it does not define the only valid client.

## Build stages

Stages are ordered by dependency. Each ends with an observable check so we can
change a weak design before building more around it. No calendar estimates are
assigned until the first technical experiment establishes the work involved.

### 0 — Establish the product and evidence

- [x] Select cross-application, user-owned memory as the working direction.
- [x] Draft the first user journey and representative memory records.
- [x] Inspect related protocols and projects for overlap and reuse opportunities.
- [x] Write this execution plan.
- [x] Demonstrate the proposed project-assistant use case internally: Claude
  proposed a real project decision, the owner accepted it, and fresh Codex
  retrieved revision 7. Independent user validation remains in Stage 5.

Existing inputs: [journey](JOURNEY.md), [readable example](MEMORY_EXAMPLE.md),
[example data](memory.example.json), and [landscape research](LANDSCAPE.md).
The example data is illustrative and contains no live approvals or grants.

### 1 — Specify the smallest interoperable contract

Deliverable: [V0 design](V0_DESIGN.md), drafted 12 October 2026. The checks below
record the specification scope. Typed schemas, cross-language fixtures, and
reference implementations subsequently landed; implementation and live evidence
are recorded in the stages below.

- [x] Define operations: read current/history, propose, accept/reject, correct,
  grant/revoke, export/import, and authorize a provider change.
- [x] Specify record identity, sources, status transitions, accepted revisions,
  base revisions, errors, and compatibility/versioning rules.
- [x] Map existing OMP concepts and identify which authority semantics require an
  explicit extension. Do not claim compatibility until tested.
- [x] Define content encoding, digest/signature boundaries, replay protection,
  identity verification, and evidence needed to verify an imported acceptance.
- [x] Define the key holder, encryption boundary, authenticated access path,
  recovery process, cache behavior, and provider migration procedure. State who
  can see plaintext and what happens when that party is unavailable.
- [x] Decide what metadata would be public and how authorization changes affect
  keys and future reads. Minimize public linkage of users, apps, and projects.
- [x] Write one complete example of two conflicting proposals, an owner correction,
  and migration with the authority evidence preserved.

Exit check: the operations and examples are precise enough for two clients to
agree on the current accepted state without depending on undocumented SDK behavior.

### 2 — Test Monad's role before committing to it

Deliverable: [local authority experiment and decision record](AUTHORITY_EXPERIMENT.md).
The local comparison and subsequent live Monad confirmation/recovery checks pass.
Encrypted storage and the live adapter are implemented. Controlled latency evidence
is documented in MONAD_PERFORMANCE.md; independent user value and broader load/cost
validation remain open.

- [x] Implement a signed portable revision-log baseline for comparison.
- [x] Build a minimal contract locally with owner-controlled permissions and an
  accepted head updated only against the expected prior revision.
- [x] Exercise competing updates, revoked permissions, replayed approvals, and a
  provider presenting a stale or conflicting history.
- [x] Compare how two independent clients discover the accepted head with and
  without a common chain. Include the assumptions each approach needs.
- [x] Specify the boundary between storing encrypted content and accepting its
  commitment, including unavailable content, failed transactions, and retries.
- [x] Specify confirmation/finality handling and behavior during RPC failure.
  Stale or unverifiable state must not be presented as freshly verified.

Exit check: demonstrate a concrete coordination benefit over the baseline and
document cost, latency, availability, privacy, and trust tradeoffs. A signed log
may be sufficient when everyone trusts one coordinator; the chain is being tested
for independent parties. It does not establish truth or guarantee data availability.
If that benefit is weak, revise the design before further Monad integration.

### 3 — Build one complete local path

Deliverable: [owner review, encrypted service and two-client flow](MEMORY_SLICE.md).
The deterministic slice supports signed-log and local registry authority.
[Registry-backed commits and crash recovery](REGISTRY_SERVICE.md) pass locally.
[Assistant adapters](ASSISTANT_ADAPTERS.md) now pass with controlled model
responses. A [three-call live Anthropic check](LIVE_MODEL_CHECK.md) also passes;
this is a bounded integration result, not a model-quality benchmark.

- [x] Create a project and record selected context with provenance.
- [x] Connect A and B with distinct scoped identities.
- [x] Let A propose a decision, the owner accept it, and B retrieve it.
- [x] Handle corrections and conflicts without losing status or history.
- [x] Enforce access withdrawal at the actual read/write boundary.
- [x] Integrate the signed-log authority mechanism and show verification status.
- [x] Connect the persistent service to the local registry with recoverable commit intents.
- [x] Add planning/coding adapters with structured generated advice, preserved
  citations, current-state rechecks and owner-reviewed proposals. Test using
  controlled model responses against the real local service and registry.
- [x] Validate actual model responses and citation quality in a bounded live run
  using synthetic memory, with generated changes gated by fixture-owner approval.

Use the existing agent runtime for one client if helpful. Make the second client
exercise the documented interface independently so success is not merely two
instances of one SDK sharing the same assumptions.

Exit check: a user can complete the main journey without database edits or manual
copy/paste between apps. Show a clear review flow and actionable conflict errors.

### 4 — Prove portability and failure behavior

Deliverable: conformance fixtures and [backend migration evidence](RECOVERY_MIGRATION.md).
Migration passes between two isolated instances of the reference provider.
Independent provider implementation compatibility remains open.

- [x] Export records, sources, revision relations, and verification evidence.
- [x] Restore through an encrypted archive and separate owner-held recovery key;
  generate fresh project keys and protect them in encrypted capsules. No keys
  appear in logs or ordinary plaintext exports. OS keychain integration remains.
- [x] Import into a second isolated reference-provider instance, verify the package,
  and require owner approval for locator, audience and grant rebinding.
- [ ] Repeat import with a separately implemented provider.
- [x] Stop the original provider and start a fresh client with no old cache.
- [x] Continue reading and proposing while preserving the logical project identity.
- [x] Test tampered exports, forged approval labels, stale caches, unavailable
  content, revoked clients, interrupted migration, and recovery from backup.

Exit check: the new provider supports continued work without contacting the old
one. A failed or incomplete import cannot replace verified current state. Report
exactly which privacy and trust boundaries remain; do not promise remote forgetting.

### 5 — Validate a live integration and prepare the demonstration

Deliverable: reproducible testnet demo, integration guide, and evidence report.

- [x] Implement the finalized-state Monad testnet adapter and independent client
  verification; pass controlled finality and recovery tests. See [adapter report](MONAD_TESTNET.md).
- [x] Probe public testnet RPC read-only and prepare an unsigned deployment artifact.
- [x] Configure a dedicated funded testnet wallet and durable deployment submission.
- [x] Deploy the validated registry to Monad testnet and verify its finalized receipt.
- [x] Host an isolated memory service outside the local machine and verify remote
  signed access, restart recovery and stopped-backup restoration. See [hosting](HOSTING.md).
- [x] Configure the dedicated DNS record and HTTPS route, then verify public access.
- [x] Exercise planning/coding against the hosted HTTPS service with live model
  calls, pending-versus-accepted context, exact correction approval and revocation.
  See [the reproducible walkthrough and limits](HOSTED_WALKTHROUGH.md).
- [x] Connect installed Claude Code through a local MCP bridge and a separately
  granted application identity; verify current reads, pending proposals and
  rejection of owner-only operations. See [integration evidence](CLAUDE_CODE_INTEGRATION.md).
- [x] Repeat conflict, revocation and migration checks against the deployed registry
  with local services. See [live test report](LIVE_MONAD_CHECK.md).
- [x] Record measured retrieval/acceptance latency, transaction cost and failure
  behavior with test conditions and sample counts. One authority interruption was
  recovered in the baseline. A second complete run passed without interruption.
- [x] Reduce repeated RPC connection overhead and batch independent verification
  reads without caching authority or weakening checks. See [performance evidence](MONAD_PERFORMANCE.md).
- [ ] Publish clear setup, operations, threat assumptions, recovery instructions,
  and examples when the project is ready for release.
- [x] Package a local signed-log developer exercise with fresh identities,
  scoped MCP config, exact owner review and a clean-environment smoke check.
  See [developer kit](DEVELOPER_KIT.md).
- [ ] Run the exercise with an independent developer. Any outreach
  is a separate action requiring user authorization; do not invent adoption.
- [x] Provide local owner inbox/app inspection and exact approve/reject/revoke
  confirmation, with durable interrupted-request recovery; validate locally and
  preview the existing hosted proposal without approving it. See [owner commands](OWNER_CLI.md).
- [ ] Observe whether users can resume work across apps with less re-explanation
  and without mistaking proposals for decisions.
- [ ] Prepare a demo showing the complete user journey and explain Monad's exact
  contribution. Re-check submission requirements when packaging the entry.

Exit check: someone outside our implementation can follow the documentation and
reproduce the core behavior. Separate local tests, live tests, internal integrations,
and external usage in all claims. Winning is an ambition, not an acceptance criterion
we can guarantee.

## Reuse strategy

Use [the landscape review](LANDSCAPE.md) as the starting comparison. Evaluate OMP
for record mapping, UOMP for scoped access, and Lethe for the onchain-memory
baseline. Consider Mem0 or Graphiti only when retrieval needs justify them.

Prefer small adapters and established cryptographic libraries. Check selected
components' actual licenses and dependencies before copying code. No repository
has been selected to fork, and no upstream implementation has been adopted yet.

## How we will execute and track progress

Work on one end-to-end behavior at a time. Update this checklist when work is
verified, link its evidence, and record architecture decisions in `V0_DESIGN.md`.
Tests should protect authority, conflicts, privacy boundaries, and interoperability;
visual polish follows a functioning path. Keep the memory prototype isolated from
the existing runtime until an integration is warranted.

The developer setup exercise is now packaged as a self-contained local signed-log
kit; see [the artifact and validation](DEVELOPER_KIT.md). The next validation is
**an independent developer following it without implementation help**, plus
repeated real usage. Hosted Monad onboarding remains separate from the local kit. The synthetic owner approval loop completed at
revision 5, and a separate Codex identity was granted at revision 6. The owner
accepted the real project-separation decision at revision 7; a fresh Codex run
retrieved it through MCP without the answer in its prompt. Claude's MCP identity
also read the same checkpoint. See [the handoff and evidence](CODEX_INTEGRATION.md).
This completes one internal real-decision workflow across two model hosts;
independent developer adoption and measured user benefit remain unproven.
Public HTTPS, owner-local approval, two-client verification and earlier
restart/backup restore checks pass.
Its own resource limits and network preserve the existing projects. Vercel DNS and
Tierhive TLS are active for `memory.useroot.xyz`; signed public reads pass independent
verification. See [the rollout and exact boundary](HOSTING.md). The
[latency milestone](MONAD_PERFORMANCE.md) also passes. RPC tail latency under load,
independent-provider compatibility and production key custody remain open.

## Owner dashboard — current frontend slice

See [frontend setup and boundaries](FRONTEND.md). This is an owner-local dashboard
for existing projects, not public account/wallet onboarding.

- [x] Copy the supplied template into `frontend/ui`, preserving the original and
  the earlier `ui/app.ts` prototype. Keep landing CSS and the 3D scene unchanged.
- [x] Adapt landing content and add overview, memory, review, connected-app and
  settings views with the template's visual style.
- [x] Add a loopback companion that reuses owner verification, exact approval,
  rejection, revocation, encrypted recovery and the CLI's operator lock.
- [x] Exercise a browser approval and verify the accepted result through both
  isolated sample app identities; test authentication and failure boundaries.
- [x] Check mobile navigation, search/filtering and review cancellation.
- [x] Recheck the hosted dashboard after the public HTTPS route is restored.
  Tierhive's IP-hostname root health probe was rejected by nginx. A health-only
  virtual host fixes the mismatch; all nine public transport checks now pass.
  The browser retrieved revision 7 through public HTTPS and verified Monad state,
  three accepted records, superseded history, and scoped application grants.
  No project records or grants changed. All running containers remained intact.
- [x] Decide wallet custody and implement isolated wallet-owned project creation
  and recovery in a local preview. The user chose their own wallet. The browser
  constructs the exact genesis and transaction; the service durably stages content
  without any wallet key or relayer. See [ONBOARDING.md](ONBOARDING.md).
- [ ] Validate creation and recovery using a real user wallet, then implement
  wallet-owned application enrollment and connect the full review dashboard.
- [ ] Publicly deploy onboarding after admission controls, resource limits, and
  backup/recovery validation. The existing hosted project stays separate.
- [ ] Implement reviewed export/migration in the dashboard after its onboarding
  and recovery flow is agreed; existing operator tools remain the supported path.

## Beyond V0

If V0 proves useful, expand integrations, improve recovery and key management,
support richer retrieval and selective sharing, and develop compatibility tests
for third-party implementations. Multi-owner projects and delegated acceptance
require a separate authority design. The long-term outcome remains the same:
users can carry useful, interpretable memory between applications without giving
one application permanent control over it.
