# Portable Memory frontend

The retained React/Vite/Three.js template is in `frontend/ui`. The original iCloud
project was not edited. `frontend/template-baseline.json` records the source file
hashes before adaptation. The copied `src/styles.css` and `src/scene.js` remain
byte-identical to the supplied template. Landing content, destinations, and gallery
illustrations were adapted; pricing/testimonial slots now describe actual preview
workflows and ownership properties. There are no invented customer endorsements.

The existing `ui/app.ts` / `web/` disposable demo is preserved.

## Run

From the repository root:

```sh
npm --prefix frontend/ui ci
npm --prefix frontend/ui run build
```

Choose one of these companions:

```sh
# Isolated illustrative state, with a pending proposal to review.
# No model calls, blockchain transactions, or hosted-project changes.
.mcp-venv/bin/python ops/dashboard_demo.py

# Existing configured Monad testnet project, owner key kept on this Mac.
.venv/bin/python ops/dashboard.py --hosted

# An existing developer-kit project, with its memory service already running.
.mcp-venv/bin/python ops/dashboard.py --state /absolute/path/to/workspace
```

Open the private one-use link printed by the companion. Its pairing code expires
in 20 minutes and is removed from the browser URL on arrival. Do not share the
link. Pairing creates an eight-hour HttpOnly, SameSite=Strict session. Restart the
companion for a new pairing link after disconnection. The companion binds only to
127.0.0.1, requires its exact Host and same Origin for writes, and sends no CORS
allowance. Sessions are in process memory and do not survive restart.

`npm --prefix frontend/ui run dev` runs the landing and disconnected dashboard
for visual work only; Vite alone has no owner API. The built companion serves the
site and API from the same origin. Neither browser localStorage nor the frontend
bundle contains owner keys. This is a trusted local owner service, not a sandbox
against malicious programs running as the same OS user. Loopback cookies do not
provide isolation from other malicious local services. Do not publish this
companion on a public interface or add a wildcard proxy/CORS configuration.

## Working dashboard behavior

- Overview: accepted records, sources, pending-review count, valid app grants,
  and the revision verified on the last refresh.
- Memory: text/type filtering, source expansion, record identity, and verified
  earlier records that were superseded or retracted.
- Review: signed proposals, current/pending/resolved status, stale-base handling,
  full replacement/retraction content and sources, exact confirmation, rejection.
- Connected apps: grants, expiry, read/propose rights and reviewed revocation.
  Active means a valid grant, not proof that the model host is currently online.
- Settings: project/owner identity, authority mode, checkpoint and explicit
  privacy/recovery boundaries.
- Interrupted confirmed writes: inspect/retry the same encrypted owner journal
  with the existing Owner.resume implementation. No acceptance is reported until
  verification succeeds. CLI and dashboard use the same operator lock/journal.

A browser confirmation is bound to the saved action, target, and checkpoint;
replacing the preview in another CLI/browser invalidates the old confirmation.
Network errors do not silently become success. Unverifiable current context is
not displayed as freshly verified. Retrieved text is rendered as text, never HTML.

## What this slice does not implement

The companion does not implement public accounts, browser wallets/passkeys,
new hosted project creation, automatic application grants, or UI-driven
export/migration. A separate own-wallet creation/recovery preview now exists at
`/start`, served by `ops/onboarding.py`; see [ONBOARDING.md](ONBOARDING.md).
It is not yet deployed publicly or connected to this companion dashboard.
Existing setup/operator tools provide their documented operations. Do not present the local
companion as public SaaS onboarding. A static frontend deployment by itself cannot
use the Mac's signing key or the hosted signed API.

The demo uses two scoped sample identities and direct MCP bridge client reads;
it does not run Claude or Codex model turns. Original live model-host evidence
remains documented in CODEX_INTEGRATION.md.

## Validation — 13 October 2026

- Vite production build passed. Three.js produces a >500 KB landing bundle
  warning; the dashboard is lazy-loaded separately and does not load the scene.
- Six new HTTP companion tests pass: authentication, single-use pairing,
  Host/Origin checks, path traversal rejection, exact review confirmation,
  lost-response recovery without duplicate commit, invalidated CLI previews,
  session expiry, unsupported operations, and fail-closed reads.
- Ten existing owner CLI tests pass.
- Browser sample flow: reviewed observation, explicitly accepted it, verified
  revision 3, refreshed the inbox, searched/filtered accepted memory, inspected
  revocation and cancelled it. Both sample app identities subsequently retrieved
  the same checkpoint and three records. See `results/dashboard-cross-app.json`.
- Checked desktop at 1440px and mobile at 390px. No horizontal overflow. Closed
  mobile navigation is hidden from keyboard/accessibility navigation.
- Original template source hashes and copied scene/stylesheet match baseline.
- Live hosted validation passed after repairing the Tierhive health-probe
  mismatch (see HOSTING.md). All nine public transport checks pass. The browser
  recovered using Try again and displayed Monad-verified revision 7, three
  accepted records, one superseded record with provenance, and application grants.
  No approvals or permission changes were submitted. See
  `results/dashboard-hosted-live.json` and `results/dashboard-hosted-live.png`.
- Outage recovery now retains the authenticated browser connection and offers
  Refresh/Try again instead of asking for an already-consumed pairing code.
  Verified this against the actual outage and subsequent successful retrieval;
  the updated production build passes.

## Next implementation steps

Private diagnostic reads first established that the stored workspace and Monad
verification were intact (`results/dashboard-private-hosted-read.json`). The
subsequent public-route repair and browser validation completed that check.
Only the memory proxy configuration was updated and reloaded; container IDs and
start times are unchanged, and Toluva/ VirgoEye public endpoints still return 200.

1. Validate the separate own-wallet creation/recovery preview with a real wallet;
   custody is agreed and creation is implemented. Then add reviewed assistant
   enrollment and connect the full dashboard. See [ONBOARDING.md](ONBOARDING.md).
2. Put the proven review/handoff flow in front of an independent developer.
