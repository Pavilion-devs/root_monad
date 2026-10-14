# Portable Memory frontend

Retained React/Vite landing template with a separate owner dashboard under `/app`.
The original template project is unchanged. Landing CSS and the 3D scene are
preserved; dashboard styles are separately namespaced.

```sh
npm ci
npm run build
```

From the repository root, launch the built site and its local owner API:

```sh
.mcp-venv/bin/python ops/dashboard_demo.py
# Or, after confirming hosted service availability:
.venv/bin/python ops/dashboard.py --hosted
```

`npm run dev` is a visual preview only. Use the private connection link printed by
the companion for actual memory operations. See `../../FRONTEND.md` for the
implemented boundary, security model, validation, and remaining onboarding work.
