# Agentic Prism application bundle

This directory is a **standalone copy** of everything required to deploy Agentic Prism in a new GCP project. It is shipped inside the `migration/` zip — you do **not** need the parent `agentic-prism-v3` repository.

## Contents

| Path | Purpose |
|------|---------|
| `agentic-lens/agents/` | 12 ADK agents (supervisor, departments, squads) |
| `agentic-lens/glass_ui/` | React Glass Lens frontend |
| `agentic-lens/security/` | IAM, Model Armor, VPC-SC, KMS Terraform |
| `backend/` | FastAPI pipeline (supervisor, armor, departments) |
| `glass_ui_api.py` | Cloud Run entrypoint |
| `infra/` | `apply.sh` and steps 01–14 |
| `scripts/` | Engine IDs, smoke tests, utilities |
| `tests/` | pytest + `fixtures/department_scenarios.json` |
| `deploy.sh` | Deploy all Reasoning Engines |
| `deploy-glass-ui.sh` | Cloud Run Glass UI |
| `deploy_all.sh` | Optional one-shot infra + agents |
| `docs/` | DEPLOY.md, README_v3, checklists (reference) |

## Not included (created at deploy time)

- `.venv/`, `agentic-lens/.venv/`
- `.env`, `versions.env` (copy from `../config/` templates)
- `*.db`, Terraform state, `.agent_engine_config.json`

## Refresh (maintainers only)

From a full repo checkout:

```bash
./migration/sync-app-bundle.sh
```
