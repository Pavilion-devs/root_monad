# Portable memory

User-owned project context that can move between AI applications and storage
providers. Start with [the plan](PLAN.md) and [V0 design](V0_DESIGN.md).

The local memory prototype has encrypted persistence, a signed HTTP API and an
owner review screen. Two demo clients share accepted decisions and corrections;
an independent Python client verifies them over the same API. Run `npm run demo`
after installation to open the sample workspace. See [the memory flow](MEMORY_SLICE.md)
for the demo steps and current limits.

The separate authority experiment compares a portable signed log with a Solidity
registry. See [the experiment report](AUTHORITY_EXPERIMENT.md). The memory service
now also supports local registry authority with durable commit recovery; see
[the registry service report](REGISTRY_SERVICE.md). The browser demo remains in
signed-log mode. The [Monad testnet adapter](MONAD_TESTNET.md) passes controlled
finality/recovery tests, and the registry is now deployed to Monad testnet. See
[wallet custody](TESTNET_WALLET.md) and the [passing live journey](LIVE_MONAD_CHECK.md); the memory service remains
local for the original journey. A separate [VPS deployment](HOSTING.md)
now passes cross-app approval, restart/backup recovery and independently verified
signed reads over public HTTPS at `https://memory.useroot.xyz`. It hosts the API;
the browser demo remains local. The [latency comparison](MONAD_PERFORMANCE.md)
records connection reuse and batched verification against the original baseline.
The [hosted assistant walkthrough](HOSTED_WALKTHROUGH.md) now passes three live
model calls through proposal, correction approval and coding-access revocation.
Those planning/coding profiles are reference adapters sharing one implementation.
The first [external application integration](CLAUDE_CODE_INTEGRATION.md) now also
passes: installed Claude Code reads verified hosted memory and submits a pending
proposal through a scoped local MCP bridge. Owner signing remains separate.
Use the [owner commands](OWNER_CLI.md) to inspect suggestions and app permissions,
then review and explicitly confirm approvals, rejections or revocations locally:
`./memory inbox`, `./memory apps`, and `./memory approve PROPOSAL_ID`.

The [Codex integration](CODEX_INTEGRATION.md) adds a separately scoped identity
and a dedicated terminal launcher. The owner accepted a real project-separation decision proposed by Claude, and
a fresh Codex session retrieved it with citations at revision 7.

## Developer package

Try the [self-contained developer kit](DEVELOPER_KIT.md) for a fresh local project
without this machine's paths, accounts or keys. The package includes a quickstart
and an HTTP/MCP smoke check. It uses signed-log authority; hosted Monad onboarding
is a separate workflow.

## Run the experiment

From this directory, with Node 18 or newer, Python, and Foundry's `anvil` available:

```sh
npm ci
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
npm run typecheck
npm test
```

Verified locally with Node 18.20.8, Python 3.14.6 and Anvil 1.7.1. Python dependencies
are isolated from the agent runtime. Other Python versions have not been tested.
The tests start Anvil on an ephemeral localhost port and stop that process after
completion. They never connect to a live chain, load a real wallet, or spend funds.
Public fixture keys are test identities only and must never be funded.

## Implementation map

| Location | Purpose |
| --- | --- |
| `schemas/` | Experimental authority, request, source, record, proposal and snapshot schemas |
| `src/protocol.ts` | Canonical encoding, signature/transition validation, signed-log baseline and request gate |
| `python/protocol.py` | Independent Python encoding, validation and signing/verifying |
| `python/memory.py`, `storage.py`, `server.py` | Persistent memory service, encrypted objects and loopback API |
| `src/client-wire.ts`, `python/client.py` | Independent client implementations |
| `python/recovery.py`, `python/admin.py` | Encrypted recovery exports, verified staging and owner-approved service migration |
| `python/assistant.py` | Planning/coding profiles, verified context, bounded Anthropic transport and proposal-only output |
| `python/testnet_wallet.py`, `python/monad_deploy.py` | Keychain-protected test wallet and durable testnet deployment |
| `python/rpc_transport.py`, `scripts/profile-monad.py` | Persistent read batches and opt-in live verification profiling |
| `ops/`, `HOSTING.md` | Isolated VPS deployment, public HTTPS checks, resource limits and recovery evidence |
| `scripts/monad-exercise.py` | Opt-in synthetic live-chain journey and measured evidence |
| `ui/`, `web/` | Local owner review demonstration |
| `contracts/MemoryRegistry.sol` | Owner signature checks and expected-predecessor ordering |
| `src/chain.ts`, `python/registry.py` | Local EVM deployment, local/Monad finalized registry verification and durable transaction submission |
| `fixtures/authority-vector.json` | Fixed cross-language fixture with public test keys |
| `tests/` | Cross-language, permission, replay, competing-history and contract checks |
| `results/` | Machine-readable outputs from successful scenario checks |

The fixture is committed to disk and checked as-is by tests. Regenerate it with
`npx tsx scripts/create-vector.ts` only when intentionally revising the protocol;
review both the input changes and the independent verification results.

The authority experiment still uses an opaque test snapshot; the memory-flow test
uses full records, sources and manifests. The original TypeScript request gate is
an in-memory comparison harness. The Python memory service adds transactionally
persisted nonce receipts and encrypted response caching.

The browser demo uses public disposable signing keys and a project encryption key
held by its launcher. Ending the demo removes its temporary data. Production key custody,
OS keychain integration remains unfinished. Planning/coding adapters and the
Anthropic path pass a [bounded live check](LIVE_MODEL_CHECK.md); see
[assistant integration](ASSISTANT_ADAPTERS.md) for the API and limits. Protected recovery
and migration between isolated reference-provider instances now pass; see
[the recovery and migration report](RECOVERY_MIGRATION.md). Use sample
text only. See [the current boundaries](MEMORY_SLICE.md).

Contract cryptography uses OpenZeppelin; offchain code uses ethers and eth-account.
Dependencies are pinned in `package-lock.json` and `requirements.lock`. The compiler's
`tmp` dependency is overridden to 0.2.7 to avoid published advisories in older
versions. `npm audit` reported zero known vulnerabilities for the installed tree
on 12 October 2026; that is not a code or cryptographic audit.

## Owner dashboard

Own-wallet project creation and recovery now have a separate local preview.
See [ONBOARDING.md](ONBOARDING.md) for the run command, tested boundaries and
remaining wallet enrollment/public rollout work.

The retained landing template and new local owner dashboard are in `frontend/ui`.
See [FRONTEND.md](FRONTEND.md) for setup, tested behavior, and remaining public
onboarding work. Run the isolated preview with `.mcp-venv/bin/python ops/dashboard_demo.py`
after building the frontend. The older local demo remains available.
