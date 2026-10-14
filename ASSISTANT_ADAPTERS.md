# Planning and coding assistant adapters

Implemented on 12 October 2026. `python/assistant.py` connects two role profiles,
with separate application identities, to the existing signed memory API. These
are reference backend adapters, not integrations with an existing third-party
chat application. They share one Python implementation. The independent
TypeScript memory client continues to exercise the protocol in integration tests.

The Anthropic transport is implemented. Default tests use controlled model
responses. A subsequent [three-call live check](LIVE_MODEL_CHECK.md) passed on
13 October 2026 using synthetic memory. No UI changes were needed.
The [hosted walkthrough](HOSTED_WALKTHROUGH.md) now also passes three real model
calls against the public HTTPS service and Monad testnet, including exact owner
approval and revocation before model invocation. See its evidence for the limits
of the generated advice. The signed Python client permits 30-second hosted
requests and rejects redirects rather than forwarding signed traffic elsewhere.

## The flow

1. Read current context through the signed API. Verify owner signatures, complete
   record/source references and, in registry mode, the independently queried
   registry head. Check the application's current audience and read grant.
2. Construct a small model payload containing the user's question, current record
   text, record kind/status and source excerpts. Replace record IDs with temporary
   aliases such as `m1`. Exclude pending proposals, superseded record bodies,
   signing keys, grants, wallet identities and protocol verification objects.
3. Call the configured model once. The planning profile focuses on goals and
   decisions; the coding profile focuses on implementation steps. Neither has
   tools, approval access, code execution or a wallet. A signing identity matching
   the project owner is explicitly refused by the adapter.
4. Validate the structured response locally. Unknown citations, extra authority
   fields, invalid replacement references, duplicate JSON keys, incomplete output
   and tool-call responses fail before any proposal is sent.
5. Read and verify current context again. If the head or permissions changed while
   the model responded, discard the result. A submission also requires a current
   propose grant, checked before and after generation.
6. Return generated advice separately from citations copied from verified records.
   An optional suggestion remains a local draft by default. Only an explicit host
   `submit: true` sends it to the proposal inbox, with status `pending_owner_review`.
   Acceptance remains the existing owner's separate review/sign/commit flow.

The assistant cannot decide whether to enable submission: that flag is supplied
by the host, outside the model response. Draft mode writes nothing to memory.
A last-moment revision race is still rejected by the service's base check.
Verification is point-in-time, not a promise that the state never changes later.

## What the output means

- `advice.status: model_generated_unverified` labels all generated advice, even if
  its text claims that something is approved. It must never be rendered as an
  owner decision solely because the model says so.
- `citations` contain exact accepted record text, model aliases (`ref`), record IDs, typed status and the
  associated stored source objects. `accepted_observation` and
  `accepted_open_question` are distinct from `accepted_decision`.
- A suggestion contains a normal protocol proposal at the verified base revision.
  Its source is explicitly an `application_observation` by the relevant assistant;
  the model's suggestion is never fabricated as a user statement.
- A correction's `replaces` points to the selected current record. It does not
  supersede that record until the owner approves the proposal.

Citation validation proves that referenced records exist in the verified snapshot
and preserves their provenance. It does not prove that generated advice follows
logically from those records, or that an observation is true. The model can still
make incorrect suggestions. Likewise, the system prompt is not a proof of prompt
injection resistance: authority is protected by the limited API capabilities,
strict output handling and separate owner approval.

Protocol metadata is excluded from prompts, but private content or secrets typed
inside record text are still content. A live model run discloses the selected
question, records and source excerpts to the configured provider. Revocation
cannot recall content already sent during an in-flight model request.

## Run a live adapter

Use the installed project Python environment. Configure `ANTHROPIC_API_KEY` and
`ANTHROPIC_MODEL` through your normal protected environment setup. The model must
support the structured-output request being used; no model name is guessed or
selected automatically. Multi-workspace keys can also set
`ANTHROPIC_WORKSPACE_ID`.

Run `.venv/bin/python python/assistant.py` and supply one JSON object on stdin:

```json
{
  "url": "http://127.0.0.1:<memory-service-port>",
  "config": {
    "projectId": "<pinned project ID>",
    "owner": "<pinned owner address>",
    "domain": "<the actual domain object from your launcher>",
    "serviceId": "<current service audience>",
    "registry": {"rpcUrl": "http://127.0.0.1:<anvil-port>"}
  },
  "applicationKey": "<this assistant's scoped application key>",
  "role": "planning",
  "question": "What should we do next, given the accepted decisions?",
  "submit": false,
  "maxTokens": 2048
}
```

The angle-bracket values are placeholders, not a valid runnable configuration.
`domain` must be the real JSON object, not a string. Obtain these pins from the
trusted service setup. For signed-log mode, use its salt-based domain and omit
`registry`. Use `role: coding` and a different scoped application key for the
second assistant. The model never receives `applicationKey` or the rest of the
protocol configuration.

Do not use the project owner's signing key as an app identity. No project
storage/decryption key is required by either assistant. Private keys belong in
protected startup input, never in command arguments or committed config files.

The API path uses one bounded request, a 45-second timeout, a configurable output
budget of 256–4096 tokens and no automatic retries. It rejects model responses
above 128 KiB and model prompt payloads above 32 KiB rather than silently dropping
memory. A token-limit stop is an incomplete response and cannot create a proposal.
The adapter does not read `.env` files or search other projects for credentials.

A lost proposal-submission response returns `submission_unknown`, preserving the
proposal ID and content. Check the app's inbox for that ID before retrying. Do not
rerun generation blindly and assume it will create the same proposal. Ordinary
service rejections remain errors. The host is responsible for retaining the
returned state; the adapter itself does not persist conversation transcripts.

Anthropic request fields follow its official [API overview](https://platform.claude.com/docs/en/api/overview)
and [structured output documentation](https://platform.claude.com/docs/en/build-with-claude/structured-outputs),
checked on 12 October 2026. API schema constraints unsupported by the provider are
omitted from the transmitted schema but enforced by the local validator. A bounded live run with the configured model now passes; the sample and its
limits are recorded in [the live report](LIVE_MODEL_CHECK.md).

## Repeatable checks

```sh
npm run typecheck
npx tsx --test tests/assistants.test.ts
.venv/bin/python -m unittest discover -s tests -p 'test_assistant.py'
npm test
```

The end-to-end check starts a real local registry and HTTP memory service, then
runs planning and coding adapters as separate processes with distinct app keys.
Only the model completion is a fixture. It proves pending content stays out of
prompts, drafts do not write, owner review gates acceptance, corrections reach the
next assistant run, sources survive, and observations retain their distinct type.
See [the recorded result](results/assistants.json).

Unit checks cover fabricated citations, authority fields, incomplete/refused/tool
responses, duplicate JSON keys, stale context, revoked and read-only grants,
owner-key misuse, tampered retrieved records, model mutation of its prompt copy,
lost submission responses and the Anthropic HTTP request shape. A mocked HTTP
request does not validate an actual model endpoint.

Full deterministic verification: 21 TypeScript checks and 30 Python tests pass.
Three live Anthropic calls additionally checked citation quality and the
owner-review boundary on sample memory. Independent provider compatibility,
OS keychain custody and live Monad finality remain separate work.
