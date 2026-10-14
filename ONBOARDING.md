# Own-wallet onboarding

Decision: the user chose own-wallet onboarding on 13 October 2026. Project authority
belongs to the connected wallet. The service must never ask for its seed phrase or
private key, generate an owner key on the user's behalf, or use the existing hosted
project's owner key for new users.

## Implemented first milestone

A separate service and `/start` screen create and recover wallet-owned projects on
the pinned Monad testnet registry. This is a local preview of the new service, not
a public rollout or a completed replacement for the existing owner dashboard.

1. Connect an injected Ethereum wallet (including EIP-6963 discovery). Switch to
   Monad Testnet and check the deployed registry bytecode against the recorded hash.
2. Review an empty project: owning wallet, service, no memory, no application grants.
   The optional project name is browser-local and is not published onchain.
3. The browser constructs the genesis snapshot and control document, hashes them,
   and requests an EIP-712 checkpoint signature. It verifies the returned signer.
4. The service validates the signature, exact empty genesis and service binding.
   It saves an encrypted catalog entry plus the project's encrypted Memory database
   and external transaction intent before returning the transaction to the browser.
5. The browser independently reconstructs and compares that transaction. A separate
   **Create on Monad** button asks the user's wallet to submit it and pay testnet gas.
   The service has no owner key, relayer key, or spending capability.
6. **Check confirmation** asks the existing registry adapter to recover the exact
   finalized event. The browser also checks the finalized head, original genesis
   event, canonical block, receipt contents, receipt stability, and fresh authority
   timestamp through the wallet provider before showing verified creation.
7. Reloading or restarting the service preserves a pending project. The exact saved
   stage request is idempotent. A public project receipt contains the service,
   project ID, owner, registry domain and service ID; it contains no keys. Recover by
   reconnecting the owning wallet and entering that project ID on the same service.

Changing accounts or networks clears the current review/verified view. Wallet
rejection is distinguished from unknown submission. An uncertain submission is
never automatically repeated. A missing/stale RPC view never becomes success.

## Run locally

```sh
npm --prefix frontend/ui ci
npm --prefix frontend/ui run build
.venv/bin/python ops/onboarding.py --state .local/wallet-onboarding --port 51746
```

Open `http://127.0.0.1:51746/start`. The existing companion and public hosted project
use their existing ports and state. This command never loads their wallet keys.
The launcher binds loopback only and locks its state directory against a second
process. Do not point it at an existing project's state directory.

The server requires exact Host/Origin and signed project requests. No browser
session, app key, or owner key is minted by connecting a wallet. New projects use
separate encrypted databases and project-derived storage keys. The service owns
the storage master key; it can read memory plaintext. Back up the whole state
folder and protect `storage.key` separately. A project receipt restores its locator,
not its contents; it cannot recover lost service data or a lost wallet.

Existing clients can use a project-specific base URL `/p/<projectId>` with the
unchanged signed `/v0/projects/<projectId>/<operation>` body paths. No application
receives access until an owner-approved grant is finalized.

## Verification

- 8 Python tests cover durable staging/restart recovery, empty genesis, altered
  bindings, wrong signatures, capacity limits, cross-project routing and read
  denial, HTTP Host/Origin/filesystem boundaries, encrypted catalog, authority
  outages/conflicts, and external-wallet grant commit recovery.
- 4 JavaScript tests cover independent Python/browser hash/signature/calldata
  agreement, changed owner/permissions/transaction rejection, wallet cancellation
  and account/chain changes, and exact fresh finalized-event/receipt verification.
- Existing Memory, registry and owner dashboard regression tests pass.
- Production frontend build passes; desktop and narrow-screen preview inspected.
- Actual extension signing and real Monad creation in this new flow remain **not
  yet tested**. No real transaction was submitted during implementation.

Run the focused checks with:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_onboarding.py'
node --test tests/wallet-onboarding.test.mjs
```

## Remaining milestones

- [ ] Complete one creation and reload/recovery with a user's own wallet on testnet.
- [ ] Add wallet-owned assistant enrollment: create an application key in the
  application/companion, prove possession, review its exact identity, rights and
  expiry, then owner-sign a grant. Do not put application keys in download URLs.
- [ ] Connect the new wallet project to the full owner review dashboard. Its current
  `/app` flow still uses the local companion and the existing project.
- [ ] Provide recovery for expired, dropped or reverted creation transactions. The
  preview currently preserves their pending state and does not offer automatic
  resubmission. Recovery by ID alone also does not authorize resubmission.
- [ ] Add public admission/rate limiting, service backup/restore exercise and tenant
  resource budgets before deploying this service publicly. The preview has bounded
  capacity (64 projects total, 3 per wallet including pending) but is not Sybil-resistant.
- [ ] Independently validate user onboarding without implementation help.

Standard EOA wallets only for now: the registry uses ECDSA, not EIP-1271 smart wallet
validation. No mobile wallet pairing, wallet-based project discovery across service
origins, wallet loss recovery, or private end-to-end encryption is claimed.

The copied template retains inherited Vite 5 development-server audit advisories;
the preview serves built assets through the bounded Python server, not Vite. Runtime
wallet dependencies are pinned. Tooling upgrades remain a separate maintenance task.
