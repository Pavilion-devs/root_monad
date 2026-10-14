# Portable Memory — developer kit 0.1.0

Try the core workflow on your own machine: one application proposes a decision,
you review the exact change, and another application retrieves accepted memory.
This kit creates a new project and fresh owner, Claude and Codex identities.
It contains no preconfigured hosted account, private keys or funded wallet.

## What this package proves

The quickstart uses **local signed-log authority**, not Monad. You can exercise
signed proposals, owner approval, encrypted storage, scoped reads, citations,
restart persistence and revocation without a cloud account or model subscription.
The local service is the sequencer; a signed old database can still look valid
if the sequencer rolls back. This mode does not provide independent discovery of
the latest accepted revision. The separate project's Monad adapter addresses that
coordination case; deploying it is outside this package's quickstart.

This is a developer evaluation kit. Use sample text. The database is encrypted,
but local development keys are stored in separate private files (directory 0700,
files 0600). This is not production key custody or encryption against the machine's
owner. The app bridge loads only its own key; other programs running as your OS
user may still read local files. Keep the state folder private and out of Git.
There is no public HTTP deployment mode in this launcher.

## 1. Install and check

Prerequisites: Python **3.14**, a terminal, and internet access to install the
pinned dependencies. The launcher uses POSIX file locking: macOS and Linux are
supported targets; this release's clean-install check was on macOS. Windows has
not been tested. No Node, Docker, API key or faucet is needed for the smoke test.

Unzip the package, enter its top-level folder, then run:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python devkit/smoke.py
```

Expect `"passed": true`. The check uses a temporary project, tests actual signed
HTTP and MCP stdio calls, then removes only its own temporary files. It makes no
model calls and no chain transactions. It does not test independent provider
compatibility or substitute for the hands-on exercise below.

The archive's `MANIFEST.json` lists source-file SHA-256 hashes. `SHA256SUMS`, supplied
alongside the archive, checks download integrity; neither is a publisher signature.

## 2. Start your own project

```sh
.venv/bin/python devkit/memory.py init
.venv/bin/python devkit/memory.py serve
```

Leave the service running. It prints a loopback URL on an available port and saves
that address for clients. In another terminal, enter the same package folder.
Every command defaults to `.memory-workspace` in that folder. For a different
location, put `--state /absolute/path/to/workspace` before the command.

`init` refuses an existing folder. It does not overwrite keys or reset a database.
`serve` can be stopped with Ctrl+C and started again against the same state.
Accepted memory survives this restart; no new `init` is necessary. Restarting
reuses the saved port so existing review journals keep the same endpoint. If that
port is occupied, stop the conflicting local process or investigate before changing
the service address; an unresolved signed journal must not be discarded.

## 3. Complete a handoff without a model

Submit a sample decision through the Claude identity:

```sh
.venv/bin/python devkit/memory.py propose claude \
  --request-id first-decision --content "Keep the two projects in separate folders."
.venv/bin/python devkit/memory.py current codex
.venv/bin/python devkit/memory.py inbox
```

The Codex read should still have no accepted records. Copy the proposal ID from
the receipt or inbox, then review it:

```sh
.venv/bin/python devkit/memory.py approve PROPOSAL_ID
```

Read the exact text, kind, source and proposed revision. Paste the displayed full
`confirmation` value to sign, or press Enter to cancel. Reviews expire after five
minutes. If input is not a terminal, the command previews only; the same action
and ID with `--confirm CHECKPOINT_FROM_PREVIEW` confirms that saved exact preview.

```sh
.venv/bin/python devkit/memory.py current codex
```

Now the accepted decision should appear at revision 1, with a record ID and source
citation. This model-free exercise uses the named application credentials directly;
it does not claim that a Claude or Codex model took part.

## 4. Connect actual AI applications (optional)

A working Claude Code or Codex installation and its own model access are required.
Normal model/account charges apply. Run this to regenerate connection files after
moving the package or switching virtual environments:

```sh
.venv/bin/python devkit/memory.py connect
```

For Claude Code, from the package folder:

```sh
claude --strict-mcp-config --mcp-config "$PWD/.memory-workspace/connections/claude.json"
```

The generated config launches the bridge with the Claude identity. It includes
paths, not keys. Claude may present its normal folder trust or tool permission
prompts. Start with: “Use memory_current to retrieve accepted project memory.
Cite its record IDs and revision. Do not propose changes.”

For Codex, register this named stdio integration using its CLI:

```sh
codex mcp add portable-memory -- "$PWD/.venv/bin/python" \
  "$PWD/devkit/memory.py" --state "$PWD/.memory-workspace" mcp codex
```

This adds `portable-memory` to Codex's user MCP configuration. If that name already
exists, choose a different name rather than replacing your existing integration.
Alternatively merge the generated `connections/codex.toml` block into your own
project's `.codex/config.toml`, preserving its existing settings. Start a fresh
Codex session with that configuration and ask the same read question. The running
memory service must remain available. Remove a CLI-registered entry later with
`codex mcp remove portable-memory` (or the name you chose).

Both connections expose only `memory_current` and `memory_propose`. The identities
are distinct. Neither tool accepts decisions, changes permissions or signs owner
checkpoints. The supplied grants expire seven days after initialization; automatic
renewal is not implemented in this kit.

To test the full model journey, ask Claude to read current memory and propose one
new decision with a stable `request_id`, then review it with the owner command.
Ask a fresh Codex session what was accepted without pasting the answer. Compare
record IDs, sources and revision. A proposed statement is not an accepted decision.
Model access and client configuration can differ by installation; the deterministic
smoke check does not establish live model compatibility for your account.

Codex configuration reference: [official MCP commands](https://learn.chatgpt.com/docs/developer-commands#codex-mcp).

## Other commands and recovery

```sh
.venv/bin/python devkit/memory.py doctor
.venv/bin/python devkit/memory.py apps
.venv/bin/python devkit/memory.py reject PROPOSAL_ID
.venv/bin/python devkit/memory.py revoke codex
.venv/bin/python devkit/memory.py resume
```

Reject and revoke use the same exact-review confirmation flow. Revocation blocks
future guarded access, not copies already read. A stale proposal must be resubmitted
against the new current revision before acceptance; it can still be rejected.

If a confirmed request loses its response, `resume` checks for acceptance before
resending the identical request. Do not delete its journal. Expired signed requests,
conflicts or unavailable history can need investigation; there is no force reset.
For `REVIEW_EXPIRED` on an unsigned preview, prepare it again and review its new
confirmation. For `SCOPE_DENIED`, inspect grants; do not switch to the owner key in
the model's config. For connection errors, restart `serve` with the same state and
run `doctor`. No cached content is presented as freshly verified.

Preserve the **entire state folder**, including private keys, if retaining this
local project. For a simple local backup, stop the service and copy the entire
folder to private storage. A copied folder is sensitive; encrypted export and
provider migration require the separate recovery workflow, not this file copy.

## Independent developer exercise

Without reading the implementation, try install → smoke check → manual proposal →
owner approval → second-client read → restart → revoke. If you have both model
clients, repeat the proposal/read steps through the real apps.

Record your OS/Python/client versions, setup time, the step where you got stuck,
and whether you could distinguish pending from accepted content without help.
Share sanitized error codes and record/revision IDs only; never send the private
folder, keys, auth files or full terminal logs containing private project content.
No telemetry or outreach is built in. A successful run by the project's author
is not independent adoption; external feedback still needs a separate test.
