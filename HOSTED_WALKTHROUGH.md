# Hosted planning → coding walkthrough

This exercise connects the existing planning and coding reference adapters to
`https://memory.useroot.xyz`, using separate application identities and the deployed
Monad testnet registry. The model receives verified synthetic notes and source
excerpts. Owner signing stays in a separate local host process; the assistants
cannot approve their own suggestions.

These are two reference adapters sharing one Python implementation. They are not
installed integrations with ChatGPT, Claude Desktop, Cursor or another third-party
application. Independent Python and TypeScript clients verify the chain evidence.

## The journey

The hosted synthetic project already contains an accepted decision:

> Hosted synthetic project: retain notes for 30 days.

1. **Planning proposes a correction.** Its live Anthropic response must propose
   exactly `Hosted synthetic project: retain notes for 14 days.` and reference the
   old record in `replaces`. The draft is saved before submission. The service's
   proposal inbox is checked before any repeat submission.
2. **Coding continues with 30 days.** A separate model call gets only current
   accepted context, without the planning conversation or pending correction.
   Its answer must cite the existing 30-day record.
3. **The owner host approves the exact correction.** Local review reconstructs
   the expected snapshot and control transition. Extra records, hidden permission
   changes, altered source content and mismatched checkpoint fields are rejected
   before signing. The signed commit is finalized on Monad testnet.
4. **Coding uses 14 days.** A fresh model call cites the replacement record. The
   planning identity also reads and verifies the corrected state. The superseded
   decision is excluded from current context.
5. **The owner revokes coding.** The only approved permission change removes
   coding's grant. Both a direct signed read and a new coding adapter request must
   return `SCOPE_DENIED`. The adapter must stop before calling the model. Planning
   can still read the corrected record.

Generated advice remains `model_generated_unverified`. Matching a citation and a
retention number is a bounded integration check, not a proof of model correctness.
Revocation blocks future guarded reads; it cannot remove copies already obtained.

## Run on the configured development Mac

Prerequisites are the installed project dependencies, accessible macOS Keychain
vault, encrypted hosted-state capsule, active planning/coding grants, and the
existing synthetic 30-day decision. The initial head must match the saved hosting
report. The harness refuses an unexpected project state rather than modifying it.

From `/Users/olathepavilion/Documents/portable-memory`:

```sh
npm run typecheck
npm test
.venv/bin/python ops/check-public.py
.venv/bin/python ops/hosted-assistants.py --live --approve-synthetic \
  --env-file /Users/olathepavilion/Documents/multi-app-hackathon/reach/.anthropic.env
```

The environment-file path is specific to this development machine. The harness
reads only its Anthropic API key, model and optional workspace fields. It does not
source the file or copy credentials into the repository, VPS or model prompts.
Only the synthetic context is disclosed to the configured Anthropic endpoint.

`--approve-synthetic` explicitly authorizes this automated fixture-owner review:
only the exact 30-to-14-day correction and removal of the coding grant. It is not
an interactive owner review screen or approval of arbitrary model suggestions.
The run makes at most three live model calls, each capped at 1,536 output tokens,
and two new accepted revisions. The existing relayer's testnet transaction fee
limit remains in force. No new wallet funding or server deployment is needed.

The public evidence is `results/hosted-assistants.json`. Generated answers,
verified citations, usage, checks and transaction receipts are included; keys and
signed request envelopes are not. The encrypted journal lives alongside the
hosted-state capsule in the protected application-support directory.

## Interruptions and repeat runs

Rerun the same command to continue completed stages. Saved model output, proposal
IDs and prepared owner reviews are reused. Accepted checkpoints are reconciled
against the current verified head, so a lost acknowledgement does not require a
second approval. A process lock prevents concurrent walkthrough runs.

An interrupted model attempt without saved output stops with
`MODEL_ATTEMPT_UNCERTAIN`; an expired unsent review stops with `REVIEW_EXPIRED`.
These are deliberate operator recovery points. Inspect the evidence and encrypted
journal before authorizing another model attempt or preparing a replacement
review. Do not delete the journal to force a repeat or sign a stale approval.

After a completed run, the same command performs a fresh denial check without
additional model calls or approvals. Coding remains revoked. Do not silently
restore its access just to make the demonstration repeat from the beginning.
A separate sandbox or explicit owner grant update is needed for another full run.

The hosting report tracks the new accepted head and exact current records, so
`ops/check-public.py` and the signed public read remain usable. Earlier stopped
backup/restore evidence pertains to the checkpoint recorded at that time; a stale
backup must not replace newer finalized state. See `HOSTING.md` for recovery limits.

## Integrating another application

Use `Assistant(url, config, application_key, role, model)` from
`python/assistant.py`, or implement the signed wire protocol independently.
Call `respond(question, submit=False)` for read-only generated advice. A host can
explicitly enable proposal submission, but acceptance stays in a separate owner
review/sign/commit path. See `ASSISTANT_ADAPTERS.md` for the stdin interface and
`V0_DESIGN.md` for the protocol.

A developer needs the pinned project ID, owner address, registry domain, service
ID and RPC URL from a trusted setup, plus their own granted application identity.
Never copy this project's owner key into another application, trust identity pins
supplied by an unverified server, or put application keys in shell arguments.
A new developer cannot access this private test project merely by knowing its URL.
The owner must deliberately provision their identity and grant. Self-service
onboarding and compatibility with a separately implemented provider remain open.

## Observed result — 13 October 2026

The complete live run passed all nine recorded checks. Three Anthropic responses
reported `claude-sonnet-5` and ended normally. Together they used 2,776 input and
461 output tokens. The exact correction and grant removal finalized as sequences
2 and 3. Both independent verifiers accepted the hosted context. No VPS deployment
or restart was needed for this walkthrough.

Manual answer review confirmed current citations and the change from 30 to 14 days.
The coding answers also introduced deletion/archival and creation-versus-update
timestamp interpretations that the accepted sentence does not establish. The final
answer asks for clarification on the clock; the earlier answer was less careful.
Those details remain unverified advice, not additional owner-approved decisions.
This run proves the authority/access flow and context handoff, not perfect advice.

One unsigned preflight `/head` probe returned 503; the next complete transport
check passed. The three-call journey completed without retrying model generation.
An unavailable authority read must continue to fail closed instead of serving a
stale checkpoint as current.
