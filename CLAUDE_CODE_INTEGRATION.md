# Claude Code integration

The portable-memory MCP bridge gives the installed Claude Code application two
scoped tools over a local stdio connection:

- `memory_current`: retrieve current accepted records, exact source references
  and an independently verified Monad checkpoint.
- `memory_propose`: submit a suggestion to the owner's inbox. It cannot accept
  decisions, sign arbitrary messages, change grants or fund transactions.

The bridge calls the hosted signed API at `https://memory.useroot.xyz`. Every read
checks current authorization and independently verifies the returned snapshot
against Monad testnet. There is no stale-cache fallback. A new application identity
has only `read_current` and `propose`, with a seven-day grant; the earlier revoked
coding identity remains revoked.

## Credentials and application boundaries

The application private key is stored in its own macOS Keychain entry. The public
profile contains configuration pins and the Keychain entry name, not the key.
The bridge never loads the owner wallet. Its encrypted outbox stores generated
proposal IDs before sending, allowing identical retries to reconcile a lost
response without submitting a second proposal. A reused request ID with different
content fails. A proposal against an old checkpoint fails instead of silently
rebasing.

The owner provisioning command is separate from the MCP server. It checks the
exact grant-only transition locally before signing. Existing grants, accepted
records and provider configuration must remain unchanged.

This is process/tool separation on the owner's Mac, not isolation against a
compromised account on that Mac. A granted model sees returned plaintext and can
retain it. No remote MCP endpoint or OAuth service has been deployed.

## Installation and configuration

The MCP dependencies use their own environment, leaving the runtime's original
Python environment and hosted containers unchanged. The pinned official MCP SDK
1.30.0 provides the stdio server and interoperability client used here.

```sh
cd /Users/olathepavilion/Documents/portable-memory
.venv/bin/python -m venv .mcp-venv
.mcp-venv/bin/python -m pip install -r integrations/claude-code/requirements.lock
.mcp-venv/bin/python -m unittest discover -s integrations/claude-code -p 'test_bridge.py'
```

The dedicated identity is already provisioned on this development Mac. Its
public launch configuration is `integrations/claude-code/mcp.json`. That file has
absolute local paths; another machine needs its own identity, owner grant and
profile. It must not copy this machine's Keychain credentials.

Check the real stdio connection without invoking a model:

```sh
.mcp-venv/bin/python integrations/claude-code/check_mcp.py
```

A Claude subscription is unnecessary when using an Anthropic API key. API usage is
billed separately. The bounded integration exercise uses the existing configured
model/key, a $0.50 run budget, an empty temporary working directory, no built-in
file or shell tools, only this MCP configuration, no hooks or skills, and no saved
Claude conversation. It does not edit global Claude settings or attach other
projects and integrations.

```sh
.venv/bin/python ops/connect-claude.py run --live \
  --env-file /Users/olathepavilion/Documents/multi-app-hackathon/reach/.anthropic.env
```

This is a one-attempt evidence command: it refuses to repeat a marked attempt
blindly. Inspect `results/claude-code-integration.json` and the application outbox
before any recovery. The normal MCP server itself supports continued use and
idempotent proposal submissions; the command's guard protects the bounded model
exercise, not a limit of the protocol.

## Use it yourself

Open an interactive memory-only Claude Code session with the protected API file:

```sh
cd /Users/olathepavilion/Documents/portable-memory
.venv/bin/python integrations/claude-code/chat.py \
  --env-file /Users/olathepavilion/Documents/multi-app-hackathon/reach/.anthropic.env
```

Ask: `What retention rule is currently accepted? Cite its record and explain what
is still unspecified.` Reads are pre-authorized; proposal tool calls use Claude
Code's ordinary permission prompts. This launcher has no file/shell tools and
does not load other MCP integrations or project customizations. It loads the API
key and required workspace header into the child environment without placing
their values in arguments or configuration files. Interactive usage is metered
normally; the $0.50 budget belongs to the automated test, not an interactive chat.
The interactive launcher is supplied for manual use; the completed end-to-end
test used the bounded print-mode command above.

## What the real-app exercise checks

Claude Code must discover the accepted retention rule through `memory_current`;
the prompt does not supply the retention number. It then proposes a synthetic
implementation observation using the returned checkpoint and a stable request ID,
and reads again to show accepted memory did not change. The host independently
checks the signed context, exact pending proposal and application identity. It
also verifies that an owner-only operation is denied to that identity.

The suggestion remains pending. Its presence is not owner approval, and model
statements about implementation or unspecified timestamp semantics are not
accepted facts. This demonstrates one external host consuming our protocol through
MCP; it does not establish independent provider compatibility or third-party user
adoption.

## Verified result — 13 October 2026

The installed Claude Code 2.1.259 completed the real-app test using the configured
Anthropic model. Its only advertised tools were `memory_current` and
`memory_propose`. It called read → propose → read, accurately cited the accepted
14-day decision and labeled its suggestion pending. Both verifiers accepted the
unchanged checkpoint at sequence 4. The new grant was the only accepted revision;
the observation remains in the owner's review inbox.

The run reported **$0.0157675** in API usage, below its $0.50 budget. Six local
bridge tests passed, covering tampering, stale revisions, revocation, owner-key
rejection, exact tool surface, duplicate submissions and lost-response recovery.
An official MCP client also initialized the real stdio process and retrieved
verified context before the model run.

The first Claude request received an API 400 because the organization key needs
an explicit workspace header. It reported zero tokens/cost and made no tool call.
After forwarding the already-configured workspace ID with the documented custom
header mechanism, the test passed. No new credential or subscription was needed.
An initial provisioning read also returned `CONTENT_UNAVAILABLE`; a fresh read
succeeded before the grant was signed. These interruptions are retained in the
evidence instead of being counted as successful model runs.

## References

- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference): API-key bare mode, explicit MCP configuration and bounded print runs.
- [Claude Code MCP integration](https://code.claude.com/docs/en/mcp): stdio tool configuration.
- [Claude Code environment variables](https://code.claude.com/docs/en/env-vars): required custom workspace header for the existing API key.
- [Official Python MCP SDK](https://py.sdk.modelcontextprotocol.io/): protocol implementation; this integration pins the compatible 1.x API.

## Owner review

Use the separate [owner command](OWNER_CLI.md) to review the pending proposal:
`./memory inbox`, then `./memory approve PROPOSAL_ID` or `./memory reject PROPOSAL_ID`.
Each displays the exact change and requires its confirmation value before signing.
Ask Claude to read current memory again after approval; an accepted observation
retains its observation kind. `./memory apps` and `./memory revoke APPLICATION_ADDRESS`
manage permissions separately from the model.

## Owner-completed follow-up

The owner subsequently accepted the boundary-test observation at revision 5,
and a fresh interactive Claude session retrieved it alongside the 14-day decision.
A separate Codex identity was added at revision 6. The real project-separation
proposal is now pending for the next owner review; see [Codex handoff](CODEX_INTEGRATION.md).
