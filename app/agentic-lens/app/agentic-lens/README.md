# Agentic Prism — Standalone Greenfield Migration Pack

**Git repository root:** initialize and push from **this directory only** (not the parent `agentic-prism-v3/`). See [PRE_PUSH.md](./PRE_PUSH.md).

**Zip and move only this folder.** It contains:

1. **Deployment runbook** (`IMPLEMENTATION.md`, `CHECKLIST.md`)
2. **Phase scripts** (`scripts/`)
3. **Config templates** (`config/`)
4. **Reference artifacts** (`artifacts/`)
5. **Full application bundle** (`app/`) — agents, Glass UI, backend, infra, deploy scripts

You do **not** need the parent `agentic-prism-v3` repository at the destination.

## Deployment status — `agentic-lens`

| Phase | Status |
|-------|--------|
| 0 Pre-flight | **Approved** |
| 1 Infrastructure | **Approved** (2026-05-20) |
| 2 Reasoning Engines (12) | **Approved** (2026-05-20) |
| 3 Agent Gateway | **Skipped** (direct connectivity, 2026-05-20) |
| 4 Glass UI | **Complete** (2026-05-21) |
| 6 Production IAM | **Applied** (RE identity IAM + orchestrator refresh) |
| 5 Validation / IAP LB | Not started |

Details: [LEDGER.md](./LEDGER.md) · [output/sign-off.md](./output/sign-off.md)

## Directory layout

```text
migration/
├── README.md                 ← you are here
├── IMPLEMENTATION.md         ← start here at destination
├── CHECKLIST.md
├── PACKAGING.md
├── PRE_PUSH.md               ← secrets scan + git push checklist
├── sync-app-bundle.sh        ← maintainers: refresh app/ from full repo
├── app/                      ← standalone Agentic Prism (~2 MB, no venvs)
│   ├── agentic-lens/
│   ├── backend/
│   ├── infra/
│   ├── deploy.sh
│   └── glass_ui_api.py
├── config/
├── scripts/
├── artifacts/
└── output/                   ← created at deploy time (logs, engine IDs)
```

## Quick start (destination machine)

```bash
cd migration

cp config/versions.env.template app/versions.env
cp config/env.template app/.env
cp config/migration.env.example config/migration.env
# Edit PROJECT_ID, REGION, ORG_ID in app/versions.env and config/migration.env

chmod +x scripts/*.sh
./scripts/run-phased.sh
```

All phase scripts use **`migration/app/`** as the application root automatically.

## Prerequisites

- `gcloud`, `terraform`, Python 3.10+
- New GCP project (billing, org policies, Agent Gateway per your setup)
- `gcloud auth login` and `gcloud auth application-default login`

## Documentation map

| Document | Use |
|----------|-----|
| [IMPLEMENTATION.md](./IMPLEMENTATION.md) | Full phased deploy guide |
| [CHECKLIST.md](./CHECKLIST.md) | Sign-off checklist |
| [LEDGER.md](./LEDGER.md) | Per-phase status and engine IDs |
| [PACKAGING.md](./PACKAGING.md) | Zip command (this folder only) |
| [app/MANIFEST.md](./app/MANIFEST.md) | What is inside the app bundle |
| [artifacts/org-policy-preflight.md](./artifacts/org-policy-preflight.md) | Org guardrails |
| [artifacts/agent-gateway-workbook.md](./artifacts/agent-gateway-workbook.md) | Agent Gateway |

## Sanity check

See **[SANITY_CHECK.md](./SANITY_CHECK.md)** for bundle inventory, path audit, and known gaps.

## Maintainers (refresh app copy)

When the main repo changes, update the bundle before zipping:

```bash
cd /path/to/agentic-prism-v3
./migration/sync-app-bundle.sh
```

Then zip `migration/` per [PACKAGING.md](./PACKAGING.md).
