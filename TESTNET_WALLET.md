# Dedicated Monad testnet wallet

Created 13 October 2026 for this project's testnet deployment and synthetic tests.
It is a locally generated wallet, not an imported browser wallet or the public
Anvil fixtures. No real-money purchase or transfer was performed.

`python/testnet_wallet.py` creates four independent random identities: a funded
relayer/deployer, an owner signing identity and two application identities. Only
the relayer needs test MON. Owner and application signatures do not spend gas.

The wallet vault lives outside the source tree at:

```text
~/Library/Application Support/PortableMemory/monad-testnet/
  wallet.enc
  public.json
  deployment-intent.enc
```

`wallet.enc` encrypts the private keys and local storage/recovery secrets with
AES-256-GCM. Its random unlock key is stored in macOS Keychain under service
`portable-memory.monad-testnet.v1`, account `local-test-wallet`. Secrets are passed
to Keychain through stdin, not command arguments. The directory is mode `0700`,
files are `0600`, and writes flush the file and containing directory. Public
metadata is derived again and checked against the decrypted identities on load.
Repeated setup preserves the same wallet. Missing encrypted key material fails
instead of silently creating a different wallet behind an existing address.

This protects secrets at rest; this Mac and its authorized processes are still
trusted. The code decrypts keys in process for signing. No independent recovery
backup or hardware signing has been configured. Keep both the encrypted vault and
its Keychain entry: losing either prevents use of the current wallet.

## Commands

From the project directory:

```sh
.venv/bin/python scripts/monad-wallet.py status
.venv/bin/python scripts/monad-wallet.py deploy --live
.venv/bin/python scripts/monad-exercise.py --live --output results/monad-live-new.json
```

Status prints only public identities, balance and the finalized block. Deployment
requires the prepared contract artifact and checks its source hash against the
current Solidity source. It refreshes chain ID, finalized state, nonce, gas
estimate, gas price and balance before signing. Deployment has a 0.2 test MON fee
ceiling. Memory updates each have a 0.1 test MON ceiling.

The encrypted deployment intent is persisted before broadcast. It fixes signed
bytes, transaction hash, predicted contract address, sender, build and fee budget.
Resumption checks those bindings and submits identical bytes. It never silently
replaces an uncertain transaction. Successful confirmation checks canonical
finalized receipt, contract address and nonempty code, then records the runtime
code hash. A changed build requires an explicit deployment decision; rerunning
does not automatically deploy a replacement.

The exercise uses synthetic text and automated test-owner approvals. It starts
fresh, loopback-only memory services, uses the deployed registry, and saves private
state in a restricted `exercise-*` directory alongside the wallet. Each fresh
exercise invocation creates a new project and consumes test gas. Choose a new
report path for each run: existing reports cannot be overwritten by a fresh run.
For migration resumption, pass the same report path as the interrupted run. There are no
model calls or access to private documents. Its public report contains checks,
transaction identities, timing samples and fees; it excludes private keys.

## Funding and deployment evidence

The official [Monad faucet](https://faucet.monad.xyz/) supplied 5 test MON after the
user completed human verification. The finalized registry deployment is recorded
in `results/monad-deployment.json`, including contract address, transaction hash,
block identity, gas used and actual fee. Live journey results are recorded
separately in `results/monad-live.json`; only its completed checks are evidence.

If the live journey is interrupted after revocation, resume its saved migration
without replaying earlier approvals:

```sh
.venv/bin/python scripts/monad-exercise.py --live --resume-migration --output results/monad-live-new.json
```

This reuses the saved encrypted migration state and owner review, existing archive,
restored provider and transaction intent. It records the interruption in the
report. It does not convert an uncertain authority response into success. Recovery
archive keys remain separate `0600` files inside the restricted exercise directory;
the new Keychain custody applies to the wallet vault, not all legacy recovery files.
