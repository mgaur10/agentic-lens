# Migration pack — sanity check report

Last reviewed: 2026-05-20 (automated + manual audit).

## Verdict

| Area | Status | Notes |
|------|--------|-------|
| Standalone `app/` bundle | **PASS** | ~2.1 MB; 12 agents + Glass UI + infra + deploy scripts |
| Phase scripts → `app/` | **PASS** (after fix) | `_common.sh` must use `-f` for `app/deploy.sh` |
| Migration doc links (`migration/*.md`) | **PASS** | Relative links within pack |
| `app/docs/` reference links | **PARTIAL** | Some links in copied `README_v3.md` point to files not bundled |
| Optional scripts (CMEK, ADK patch) | **SKIP OK** | Missing in upstream repo too; infra steps skip gracefully |
| Hardcoded dev machine paths | **WARN** | Debug log paths in 2 Python files (non-blocking) |
| Example project ID in docs | **INFO** | `agentic-prismv333` in examples only; templates use `REPLACE_ME` |

**Ready to zip and deploy** after: configure `app/versions.env`, run `./scripts/phase0-preflight.sh`.

---

## Critical fix applied

`_common.sh` used `[[ -d "$MIGRATION_DIR/app/deploy.sh" ]]` (directory test on a **file**). Standalone zip resolved `REPO_ROOT` to the parent of `migration/` instead of `migration/app/`.

**Fixed:** `[[ -f "$MIGRATION_DIR/app/deploy.sh" ]]` → `REPO_ROOT=migration/app/`.

Verify:

```bash
# After unzip, from migration/
source scripts/_common.sh && echo "$REPO_ROOT"
# Expected: .../migration/app
```

---

## Bundle inventory (required for deploy)

| Item | Path | Present |
|------|------|---------|
| Deploy agents | `app/deploy.sh` | Yes |
| Glass UI deploy | `app/deploy-glass-ui.sh` | Yes |
| Infra | `app/infra/apply.sh` + `steps/01-14` | Yes |
| API entry | `app/glass_ui_api.py` | Yes |
| Backend | `app/backend/*.py` | Yes |
| Agents (12) | `app/agentic-lens/agents/{supervisor,chat,eng_*,events,xray_*}/` | Yes |
| Glass UI | `app/agentic-lens/glass_ui/` + `package.json` | Yes |
| Security TF | `app/agentic-lens/security/{iam,policies,vpc_sc,db}/` | Yes |
| Engine ID script | `app/scripts/get_agent_engine_id.py` | Yes |
| Env updater | `app/scripts/update_env.py` | Yes |
| Smoke test | `app/scripts/smoke_glass_ui_departments.py` | Yes |
| Pytest fixtures | `app/tests/fixtures/department_scenarios.json` | Yes |
| Cloud Build | `app/cloudbuild_glass_ui.yaml`, `Dockerfile_glass_ui` | Yes |
| DLP helper | `app/create_dlp_templates.py` | Yes |
| Config templates | `config/versions.env.template`, `config/env.template` | Yes |
| Runbook | `IMPLEMENTATION.md`, `CHECKLIST.md` | Yes |

**Agent folders (12):** supervisor, chat, eng_lead, eng_scout, eng_coder, eng_quality_and_security_reviewer, events, xray_manager, xray_librarian, xray_architect, xray_specialist, xray_auditor.

---

## Optional / missing upstream (non-blocking)

| Script | Referenced by | In `app/scripts/`? | Impact |
|--------|---------------|----------------------|--------|
| `patch_adk_config_agent_utils.py` | `deploy.sh`, infra step 11 | No (not in main repo) | Step 11 skips; deploy may still work |
| `setup_cmek_per_department.sh` | infra step 05 | No (not in main repo) | CMEK step skips; use org keys or add script |
| `grant_service_usage_to_engines.sh` | `deploy_all.sh` | No | Use `migration/scripts/grant-engine-telemetry-iam.sh` |

---

## Path and reference audit

### Safe (standalone)

- `app/infra/apply.sh` sets `ROOT_DIR` to `app/` — correct.
- `app/deploy.sh` uses `$ROOT_DIR/agentic-lens/agents` — correct.
- `app/scripts/smoke_glass_ui_departments.py` uses `parents[1]` → `app/` for fixtures — correct.
- Migration phase scripts `cd "$REPO_ROOT"` — correct after `-f` fix.
- `copy_templates_if_missing` writes to `app/versions.env` and `app/.env` — correct.

### Misleading copy text (fixed)

- Templates said “copy to repo root” — updated to `cp config/... app/versions.env`.

### Echo paths in scripts (fixed)

- `phase0`, `run-phased` now say `artifacts/...` not `migration/artifacts/...` when run from `migration/`.

### References to parent repo (intentional)

| Location | Purpose |
|----------|---------|
| `README.md`, `PACKAGING.md` | Maintainers: run `sync-app-bundle.sh` from full repo |
| `sync-app-bundle.sh` | One-way sync from parent → `migration/app/` |
| `_common.sh` fallback | If `app/deploy.sh` missing, use parent (maintainer checkout) |

### Broken / stale doc links inside `app/docs/` (informational only)

Copied `README_v3.md` links to files not in `app/docs/`:

- `CONVENTIONS.md` — not in repository
- `LOCAL_SETUP.md`, `SUPERVISOR_AUDIT.md` — not bundled
- `agentic-lens/glass_ui/README.md` — exists at `app/agentic-lens/glass_ui/README.md` (different path)

**Use for deploy:** `migration/IMPLEMENTATION.md`, `app/docs/DEPLOY.md`, `artifacts/*` — not `app/docs/README_v3.md` alone.

### Hardcoded paths (warn)

- `app/backend/debug_session_ndjson.py` — `.cursor` debug log under old workspace path
- `app/agentic-lens/agents/eng_lead/src/manager.py` — same

Does not affect Cloud Run / Agent Engine deploy.

### Example project IDs

`agentic-prismv333` appears in `app/docs/*` and `app/env.example` as **examples**. Deployment must use `config/*.template` → `app/versions.env` / `app/.env`.

---

## Pre-start checklist (operator)

```bash
cd migration
test -f app/deploy.sh && test -d app/agentic-lens/agents/supervisor && echo "Bundle OK"
cp config/versions.env.template app/versions.env
cp config/env.template app/.env
cp config/migration.env.example config/migration.env
# Edit PROJECT_ID, REGION, ORG_ID
chmod +x scripts/*.sh
./scripts/phase0-preflight.sh
```

---

## Re-run sanity after code changes

```bash
./migration/sync-app-bundle.sh
# Re-run bundle table checks above
```
