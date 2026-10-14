# Hosted testnet memory service

This deployment is isolated from the agent runtime project and other applications
on the shared Tierhive VPS. The public origin is `https://memory.useroot.xyz`.
The latest verified state is in `results/hosted-memory.json` and the rollout notes
below. A configured domain alone does not establish a working public endpoint.

## Boundaries

- Only `portable-memory`, `portable-memory-proxy`, `portable-memory-net`, and
  `/srv/portable-memory` belong to this deployment. Never restart Docker, reboot
  the VPS, prune shared images/volumes, or modify other projects to operate it.
- The app container uses UID 10002, a read-only root filesystem, dropped Linux
  capabilities, no new privileges, a 256 MiB memory limit and 0.25 CPU quota.
  Its own encrypted database directory is its only persistent writable mount.
- A separate unprivileged nginx proxy has 64 MiB RAM and 0.10 CPU quota. It buffers
  requests, bounds body size and timeouts, and rate-limits API calls. This protects
  a small serial reference server; it is not a multi-tenant production gateway.
- Private testing binds the proxy to `127.0.0.1:3014` on the VPS and reaches it
  through a separate SSH tunnel. The app itself has no published host port.
- The public proxy additionally binds `10.3.245.2:3014` for the Tierhive edge.
  There is no new public NAT port. Only this domain routes to that backend.
- Public routing must target only this proxy, with TLS active and a dedicated
  DNS record. Origin checks do not provide encryption: do not expose the HTTP
  backend directly to the internet or route private operations over public HTTP.
- `Host` and optional `Origin` must match configured pairs. Forwarded headers
  cannot override this rule. Signed authorization remains necessary for memory
  operations. `/healthz` only reports process liveness; `/head` checks chain state.
- Public deployments reject the local demo configuration because it includes
  test signing keys. No browser demo or unsigned memory-reading route is hosted.

## Key custody

Owner and application private keys remain in the local Keychain-protected vault.
A dedicated relayer received 0.5 test MON for this deployment, with a durable
funding intent to prevent accidental repeat transfers. Each memory transaction
is capped at 0.1 test MON. The relayer pays gas; it cannot approve owner revisions.

The server receives only its new storage key, dedicated relayer key and public
project configuration through authenticated SSH. They are kept in a `0600`
service-only file mounted read-only, outside the image and process arguments.
The server can decrypt memory during requests. This is encryption at rest for
stored records, not protection from the VPS administrator or compromised server.
Do not describe it as end-to-end encryption against the provider.

The local hosted-state capsule is encrypted using the existing wallet recovery
secret under the restricted `hosted-memory` state directory. The local original
wallet, owner/client keys and recovery unlock key are never uploaded. On-server
backups contain encrypted memory; keep recovery key custody separate. A same-host
backup alone does not protect against loss of the VPS.

## Implementation and operation

`ops/Dockerfile` packages the pinned Python dependencies, service and schemas.
The image is built locally for `linux/amd64` and transferred to the VPS. No source
build is required on the shared CPU. No personal files or key material belong in
the build context; the rollout uses a tar containing only the listed source files.

`ops/hosted.py` is a deliberately target-specific deployment exercise:

```sh
.venv/bin/python ops/hosted.py baseline --live
.venv/bin/python ops/hosted.py prepare --live
.venv/bin/python ops/hosted.py provision --live
```

`prepare` creates the isolated synthetic project and funds its dedicated relayer
on Monad testnet. It persists signed funding bytes before broadcast. `provision`
refuses an existing target directory; it must never overwrite a live deployment.
If provisioning is interrupted, inspect the isolated directory before resuming
individual steps. Do not delete unrelated state or blindly rerun setup.

After loading the image, run `ops/start-private.sh` on the VPS. It refuses existing
container/network names and an occupied port. It starts only these two containers.
Both use `unless-stopped`; an explicitly stopped service stays stopped.

For this existing deployment, `ops/start-public-proxy.sh` replaced only the proxy
after validating `ops/nginx-public.conf`. The original private proxy is retained
stopped as `portable-memory-proxy-before-public`. The app and its data are unchanged.
The script refuses to rerun over that retained container. To roll back, stop the
new proxy, preserve it under an unused name, rename the retained private proxy to
`portable-memory-proxy`, and start it. That removes edge access; SSH testing remains
available. Never perform this rollback against an unrelated container.

Before any public signed exercise, run `ops/check-public.py`. It uses normal
certificate validation, requires HTTP redirects even with spoofed scheme headers,
and checks unsigned access, Origin enforcement, payload limits and absence of demo
keys. The proxy's scheme header guard alone is insufficient if the edge forwards
user-supplied headers; the public HTTP test must pass at the deployed edge.

The signed exercise is run from this Mac through a tunnel on local port 13014:

```sh
.venv/bin/python ops/hosted.py write --live
.venv/bin/python ops/hosted.py restartVerified --live
.venv/bin/python ops/hosted.py backupRestoreVerified --live
```

The write exercise is a one-time synthetic proposal/approval/read, signed locally.
The verification operations compare the accepted digest and content against saved
evidence and independently verify with Python and TypeScript using public RPC.
They do not create another approval.

Only stop/restart `portable-memory` for recovery tests. Stop it before taking a
filesystem snapshot of SQLite, including any WAL state; retain the encryption key
separately. For the verified restore procedure, preserve the current data directory
under a new backup name, restore a complete stopped snapshot to a fresh data
directory, and start the same container. Do not run two writers against one project
or replace current data with a stale backup without reconciling finalized state.

To disable this deployment, stop only `portable-memory-proxy` and
`portable-memory`. Keep its private data and secrets for recovery. Public routing,
if configured, must be removed only for `memory.useroot.xyz`; leave every other
Tierhive backend and DNS record untouched.

## Verified rollout — 13 October 2026

Private deployment passed on Tierhive VPS 15496. Both new containers are running;
the app reports healthy. A client on this Mac connected through a dedicated SSH
tunnel, submitted a synthetic planning proposal, signed its approval locally,
and read the accepted decision through the coding identity. Both independent
verifiers accepted the Monad evidence.

Restarting only `portable-memory` preserved the accepted checkpoint. We then
stopped that container, saved a complete data snapshot, preserved the original
data directory, restored the snapshot to the live path, and verified the same
checkpoint/content after starting it. An encrypted copy of the stopped snapshot
was saved on this Mac and checked by decrypting its envelope. Restoring that
additional offsite envelope onto a different machine has not yet been tested.
The server snapshot is `/srv/portable-memory/backups/verified-checkpoint`;
`data-before-restore` preserves the pre-restore directory.

Remote checks rejected a wrong Origin, unsigned context access and oversized
requests, and confirmed that the demo-key endpoint is absent. The original five
containers retained their exact IDs and startup timestamps. Final memory
availability was approximately 1.2 GB and free disk approximately 9.0 GB.

Initial probes returned 502 during cold startup and restart initialization; the
exercise now waits for liveness before sending signed operations. The app has a
small CPU quota, and readiness is not instant. No other container was restarted.

Public HTTPS now passes at `https://memory.useroot.xyz`. Vercel DNS has one new
`A` record, `memory → 57.129.106.133`, with a 60-second TTL. Existing apex, wildcard
and other application records were preserved. Tierhive routes only this domain to
`10.3.245.2:3014`. Its Let's Encrypt certificate expires 11 January 2027; Tierhive
reports automatic renewal enabled. Issuance preceded edge distribution by several
minutes; validation waited until the public server actually served the certificate.

`ops/check-public.py` passed normal certificate validation and liveness/head reads.
Public HTTP returned 301 to the exact HTTPS endpoint even when the client supplied
spoofed scheme headers. Wrong Origin returned 403, unsigned context input 400,
oversized input 413, and the demo-key endpoint 404. The active Tierhive edge enforces
the redirect; do not infer this from nginx's forwarded-header guard alone.

The following signed public read passed both independent Python and TypeScript
verification against Monad testnet, preserving the previously accepted checkpoint
and synthetic content. Owner/application signing keys remained on this Mac.

```sh
.venv/bin/python ops/check-public.py
.venv/bin/python ops/hosted.py publicHttpsVerified --live --url https://memory.useroot.xyz
```

The endpoint hosts the signed API, not the local owner-review browser demo. Its
root returns 404; `/healthz` is the visible liveness check. The temporary SSH test
tunnel is closed. This is a single-project test deployment with seven-day app
grants, not production custody or a public multi-user release.

### Tierhive backend health probe

On 13 October, packet inspection showed Tierhive's checker requesting `GET /`
with `Host: 10.3.245.2:3014` from `10.0.0.3`. The default virtual host closed that
request with nginx 444, so Tierhive marked the otherwise healthy backend down
and public HTTPS returned 503. The domain's `/healthz` continued returning 200.

`ops/nginx-public.conf` now has a separate virtual host for `10.3.245.2`. Only
GET/HEAD at its exact root proxies to the app's `/healthz`. Other paths remain
closed, POST is forbidden, and unknown hostnames remain closed. This is process
liveness only; authenticated memory reads still verify Monad authority.

The candidate configuration passed nginx validation before an in-place update
and reload of `portable-memory-proxy`. All running container IDs and start times
were unchanged. The previous file is retained on the VPS at
`/srv/portable-memory/nginx-public.before-ip-health.conf`; rollback must copy its
contents into the existing mounted file and reload nginx, preserving the bind
mount's inode. See `results/route-repair-rollout.json` and
`results/route-repair-proxy-checks.json` for rollout and boundary-check evidence.

After Tierhive's next check and routing update, the backend showed Healthy and
all nine `ops/check-public.py` checks passed. The owner dashboard retrieved and
verified revision 7 through public HTTPS. Other running containers retained their
IDs and start times; Toluva and VirgoEye public endpoints both returned 200.
See `results/route-repair-public-checks.json` and `results/dashboard-hosted-live.json`.

The later [hosted assistant walkthrough](HOSTED_WALKTHROUGH.md) advanced this
project to sequence 3: the accepted synthetic retention decision is now 14 days,
and the coding grant is revoked. Planning remains authorized. The hosting report
pins the updated digest and exact current records for future verification.
The earlier stopped backup and restore checks covered sequence 1. That snapshot
is historical evidence and must not overwrite the newer finalized state.

The subsequent [Claude Code integration](CLAUDE_CODE_INTEGRATION.md) added only
a dedicated seven-day read/propose grant at sequence 4. The accepted 14-day note
is unchanged and the original coding identity remains revoked. Claude Code's
new observation remains pending. No VPS container or deployment was changed.

Final validation: type checking and all 71 local checks passed (24 TypeScript,
47 Python). Toluva and VirgoEye both returned HTTP 200 over public HTTPS from
this Mac after rollout. Their existing services and routes were preserved.

## RPC connection recovery fix — 13 October 2026

An owner command intermittently failed before review with `CONTENT_UNAVAILABLE`.
The `/head` handler previously mapped every exception to that code, including
RPC failures. It now distinguishes unavailable authority, genuinely unavailable
content, integrity errors and unexpected internal failures without exposing raw
exception text. Existing wrong-chain and missing-registry checks still fail closed.

The persistent RPC transport now retires connections idle for 10 seconds. An
interrupted reused connection gets at most one fresh-connection retry for explicitly
allowed reads. Each attempt validates fresh response IDs and contents. Invalid
JSON-RPC responses and transaction broadcasts are never automatically replayed;
there is no cached-head fallback. Regression tests cover a closed reused connection,
repeat failure, corrupt replies, idle eviction and uncertain broadcast.

The app-only image overlays `python/rpc_transport.py` and `python/server.py` on
the exact existing hosted image, without changing dependencies, storage or keys.
`ops/rollout-rpc-reconnect.py` preserves the private app address and limits, keeps
the proxy running and retains `portable-memory-before-rpc-reconnect` as a stopped,
network-detached rollback container. Never run both app versions against the same
database. Rollback requires stopping/detaching the replacement before reconnecting
and restarting the retained container at the original address.

The original live exception was masked, so its exact underlying exception is not
proven. A separate 35-second idle RPC probe succeeded; a longer SSH probe timed
out without usable diagnostic output. The stale-connection recovery is reproduced
with controlled transport failures. Live validation after rollout is recorded in
`results/rpc-reconnect-live.json`; the user's pending approval is not submitted.
