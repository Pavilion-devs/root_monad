# Packaged developer exercise

Artifact: [portable-memory-devkit-0.1.0.zip](dist/portable-memory-devkit-0.1.0.zip).
Integrity: [SHA256SUMS](dist/SHA256SUMS). Instructions: [kit quickstart](devkit/README.md).

The package contains a relocatable Python entry point, pinned dependencies,
protocol schemas, the reference service, scoped MCP bridges, owner commands,
a deterministic smoke test and a per-file hash manifest. Its allowlist excludes
our hosted configuration, private state, captured conversations, live project IDs,
Mac-specific integration scripts and credentials. The kit's generated connection
files use paths on the recipient's own machine.

A developer can create a fresh local project, propose as one application, review
as owner, read as the other application, restart, reject and revoke. Generated
Claude and Codex connection settings support optional real-model exercises with
the recipient's own installed clients and account access. The smoke test itself
uses no model or blockchain calls.

This is the **local signed-log evaluation package**. It does not automate a new
Monad deployment, hosted TLS, production key custody or provider migration. Our
separate hosted Monad demonstration remains intact at revision 7. The local kit's
private-file key storage and single-sequencer trust assumptions are explicit in
the quickstart. Cross-platform live-model setup and an independent person's use
remain unverified; no package registry publication or outreach was performed.

## Build and verify

```sh
.venv/bin/python scripts/package-devkit.py
.venv/bin/python scripts/check-devkit.py
```

The builder includes only explicit files. The check extracts the final archive
outside the source tree, creates a new virtual environment, installs the lockfile,
runs `pip check`, verifies all manifest hashes, and completes the HTTP/MCP smoke
workflow. Temporary sample state is cleaned up. See
[clean-install evidence](results/devkit-clean-install.json).

The first smoke run found that a random port changed after service restart,
invalidating the endpoint bound into an owner review journal. Restart now reuses
the saved port; the smoke workflow covers the regression. This fix is confined to
the new local developer launcher. Existing hosted service and app launchers were
not modified.

## External exercise

Give the ZIP and checksum file to a developer only when authorized. Ask them to
follow its README without implementation help, note time-to-first accepted read,
report confusing steps and sanitized errors, and distinguish pending proposals
from accepted records. Treat any failure as feedback on setup. The automated
clean-environment run is internal evidence, not external adoption.
