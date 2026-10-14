# Codex and Claude memory handoff

Codex has a separate application identity, with `read_current` and `propose`
permissions and a seven-day grant. Its key is held in the macOS Keychain under
`portable-memory.mcp.codex.v1`. Claude retains its own identity. Neither bridge
loads the owner vault or exposes acceptance or grant operations.

This is an integration with the installed **Codex CLI**, using the existing
ChatGPT login. It does not add tools to this already-running desktop conversation.
The launcher passes its MCP configuration per invocation, leaving global Codex
settings and other projects alone. The stdio bridge implementation is shared;
these are two external model hosts, not two independent provider implementations.

## Ask Codex

From `/Users/olathepavilion/Documents/portable-memory`:

```sh
.venv/bin/python integrations/codex/chat.py
```

Enter a question when prompted. Each invocation starts a fresh Codex execution in
an empty temporary workspace and prints its answer. No answer or project document
is injected. The launcher uses the installed CLI default model and the
existing login, ignores unrelated user configuration/rules, disables shell,
plugins, hooks and other integrations, and exposes only `memory_current` by default.
It has a four-minute process timeout. Account usage applies as with other Codex
runs. No OpenAI API key is copied into the environment.

A question can also be supplied directly:

```sh
.venv/bin/python integrations/codex/chat.py "Read verified project memory. What decisions are accepted? Cite the records and revision."
```

`--allow-proposals` additionally exposes `memory_propose`. These are pending
suggestions only. The command does not offer owner approval tools. This tool-level
restriction is not an OS sandbox against other programs running as the same user.

## Real project decision

Claude Code submitted this decision through its MCP identity; the owner has now
accepted it at revision 7:

> Portable memory is a separate project from the agent runtime. Keep its code and documentation in the portable-memory folder, separate from the runtime folder.

This records the user's earlier separation instruction. It lives in the existing
Monad testnet test project alongside the synthetic retention example. The MCP
source identifies it as an application observation; it is not a cryptographic
attestation of the original chat. Owner acceptance is a separate, explicit step.

Review it with:

```sh
./memory approve 0x789d043a7b5f2bbdbb16cb73f2a018b7b561da07a7c61cf91e659c6a64140640
```

Paste the fresh confirmation shown by the command only if you agree. If it returns
`COMMIT_PENDING`, use `./memory resume`. Do not reuse a confirmation from these docs.

After approval, ask Codex:

```text
Use memory_current to read verified project memory. What accepted decision describes the relationship between these projects? Cite its exact record ID, source and revision. Do not propose changes.
```

The question intentionally omits the decision's answer. Before approval, that
pending decision must not appear among current accepted records. After approval,
Codex should retrieve it along with its record kind, citation and current revision.
Ask Claude the same question to compare the two independently authenticated reads.

## Reproducible checks

- `ops/connect-codex.py --live` provisions only the separately authorized Codex
  grant, preserving existing grants and records. An encrypted journal saves the
  exact signed grant request before transmission; replay reconciles its accepted
  checkpoint. It does not silently renew or restore a revoked grant.
- `ops/cross-app.py propose --env-file PATH` uses installed Claude Code, with a
  $0.50 run budget and one stable proposal request ID. It has already run; its
  attempt guard prevents silently repeating a charged or uncertain proposal run.
- `ops/cross-app.py read` runs a fresh installed Codex process with only the read
  tool enabled, checks actual MCP tool events, checks answer content/IDs against
  independently verified memory, and confirms that accepted state did not change.
  This read is repeatable and uses account capacity.
- `./memory apps` lists both named identities. The original coding reference
  identity remains revoked.

Evidence: `results/codex-identity.json`, `results/real-project-proposal.json` and
`results/codex-memory-read.json`. The latter records whether the proposed real
project decision was accepted at the time of the read; a passing connection test
is not proof of the post-approval handoff. These are internal tests, not evidence
of independent adoption, generic provider compatibility or measured user benefit.

Configuration follows the [official MCP command documentation](https://learn.chatgpt.com/docs/developer-commands#codex-mcp)
and [official Codex configuration example](https://learn.chatgpt.com/docs/config-file/config-sample),
with flags checked against installed Codex CLI 0.154.0. No remote MCP server,
OAuth bridge or global MCP registration is required for this local stdio setup.

The first test rejected the desktop-configured model alias before any tool call.
The terminal launcher therefore uses its own default model without changing
desktop settings; the initial failure is retained in `results/codex-read-initial-failure.json`.

## Completed owner handoff — 13 October 2026

The owner confirmed the project-separation decision, and `memory resume` verified
revision 7. A fresh installed Codex run then called `memory_current` and returned
all three accepted records with exact content, kinds and citations. The prompt
did not contain the decision or its record ID. Claude's scoped MCP connection
also independently retrieved the same checkpoint and three records; this latter
check used the MCP client, not another Claude model turn.

Evidence: `results/codex-memory-read-after-project-approval.json` and
`results/claude-mcp-after-project-approval.json`. The pre-approval Codex read remains
in `results/codex-memory-read-before-project-approval.json`. The full
Claude proposal → human review → Codex retrieval path now passes for one real
project decision in the existing testnet workspace.
