# Migration sign-off checklist

Work from the **`migration/`** directory. Config: **`app/versions.env`**, **`app/.env`**, **`config/migration.env`**.

Copy this file or print sections per phase. Store completed copy in `output/sign-off.md`.

**Project ID:** `agentic-lens`  
**Region:** `us-west1`  
**Date:** 2026-05-20  
**Operator:** ___________________

---

## Phase 0 — Pre-flight

- [ ] `app/versions.env` configured (no `REPLACE_ME`)
- [ ] `config/migration.env` configured (from `config/migration.env.example`)
- [ ] `app/.env` created from `config/env.template`
- [ ] `REPO_ROOT` resolves to `.../migration/app` (`source scripts/_common.sh`)
- [ ] `gcloud` + ADC authenticated
- [ ] `ORG_ID` set or auto-resolved
- [ ] `org-policy-preflight.md` reviewed
- [ ] `agent-gateway-workbook.md` reviewed
- [ ] `phase0-preflight.sh` completed

---

## Phase 1 — Infrastructure

- [ ] Step 01 APIs enabled
- [ ] Step 02 Agent Engine bootstrap
- [ ] Step 03 secrets (PAT skipped or created)
- [ ] Model Armor (step 04 or org equivalent)
- [ ] CMEK keys in `app/versions.env` (step 05 or org keys)
- [ ] IAM Terraform step 06
- [ ] Firestore step 07
- [ ] Telemetry (if `RUN_TELEMETRY=1`)
- [ ] Artifact Registry step 09
- [ ] Events KB (if `RUN_SETUP_KB=1`) — data store ID in `app/.env`
- [ ] VPC-SC (repo step 12 or org perimeter documented)
- [ ] RAG steps 13–14 (if run)
- [ ] `phase1-infra.log` archived

---

## Phase 2 — Agents

- [x] Agent sources validated: `./scripts/validate-phase2-agent-sources.sh` (after `sync-app-bundle.sh` if agents changed in repo)
- [x] `gcloud auth application-default set-quota-project agentic-lens`
- [x] Failed/orphan engines removed in Console (before deploy) — optional cleanup ongoing
- [x] Step 1 — 9 specialists deployed (`SKIP_PREFLIGHT=1`)
- [x] Peer engine IDs merged (`merge_peer_engine_env.py`)
- [x] Step 2 — `eng_lead`, `xray_manager`, `supervisor` deployed
- [x] `grant-engine-telemetry-iam.sh` completed
- [x] `grant-reasoning-engine-identity-iam.sh` completed (RE principal `aiplatform.user`)
- [x] `eng_lead` + `xray_manager` refreshed after peer merge (in `phase2-agents.sh` step 3)
- [x] `write-engine-ids-to-env.sh` completed — 12/12 engine IDs in `app/.env`
- [x] `AGENTIC_LENS_SUPERVISOR_ENGINE` and `AGENTIC_LENS_ENGINE_SCOUT` in `app/.env`
- [x] Department engine IDs in `app/.env`
- [x] Engineering squad IDs in `app/.env`
- [x] `./scripts/verify-phase2-engines.sh` — 12/12 OK
- [x] Engines visible in Vertex Console
- [x] Phase 2 sign-off recorded in `LEDGER.md` and `output/sign-off.md`

---

## Phase 3 — Agent Gateway

**Skipped for `agentic-lens`** (`SKIP_AGENT_GATEWAY=1` — direct Reasoning Engine connectivity)

- [x] Skip documented in `LEDGER.md` / `IMPLEMENTATION.md` §8.0
- [x] No `AGENT_GATEWAY_*` in `app/.env` (not required)
- [x] Phase 3 sign-off — deferred / N/A (2026-05-20)
- [ ] _(Only if enabling gateway later)_ workbook `artifacts/agent-gateway-workbook.md`

---

## Phase 4 — Glass UI

- [x] `deploy-glass-ui.sh` succeeded (`output/phase4-glass-ui.log`)
- [x] `/api/healthz` returns 200
- [x] `/api/healthz?deep=1` — supervisor configured
- [ ] Manual query — not `[Mock]`
- [ ] Auth mode documented (public dev / IAP)

---

## Phase 5 — Validation

- [ ] `pytest tests/` pass
- [ ] `smoke_glass_ui_departments.py --profile smoke` pass
- [ ] Optional: `--profile full`
- [ ] Cloud Logging events visible
- [ ] Gateway audit (if applicable)

---

## Phase 6 — Production edge

- [x] `grant-reasoning-engine-identity-iam.sh` (RE principals — peer `reasoningEngines.get`)
- [ ] `eng_lead` / `xray_manager` redeployed after peer merge (if peers added later)
- [ ] HTTPS LB + serverless NEG
- [ ] Managed certificate
- [ ] IAP enabled
- [ ] IAP → Cloud Run invoker binding
- [ ] Backend timeout ≥ 1800s
- [ ] Smoke with IAP passes
- [ ] Legacy `agentic-lens-ui` removed (if existed)

---

## Final

- [ ] `resource-inventory.csv` filled
- [ ] `engine-ids.env` archived
- [ ] Runbook handed to operations

**Signed:** ___________________  **Date:** ___________________
