# Deployment Guide: agentic-prismv333

This guide walks you through deploying **Agentic Prism** to GCP project **agentic-prismv333**.

---

## Before a fresh install (new project)

If you are switching to a **new GCP project** and want a clean slate (no leftover Terraform state, venvs, or agent configs), run:

```bash
./scripts/clean_for_fresh_install.sh
```

Use `-f` or `--force` to skip the confirmation prompt. Then set `PROJECT_ID` (and `REGION`, `MODEL_VERSION`) in `versions.env` and run `./deploy_all.sh`.

---

## Quick deploy (one script)

Set **PROJECT_ID**, **REGION**, and **MODEL_VERSION** in `versions.env`, then run:

```bash
./deploy_all.sh
```

The script creates root and agentic-lens virtual envs if missing, runs infrastructure, deploys all agents, and writes **AGENTIC_LENS_SUPERVISOR_ENGINE** (and project number) to `.env`. No manual copy-paste or intermediate steps. Optionally use `RUN_SETUP_KB=1 ./deploy_all.sh` to create the Events data store and set `VERTEX_SEARCH_DATA_STORE_ID` in `.env`. When it finishes, test the UI locally or run `./deploy-glass-ui.sh`.

---

## Prerequisites

- **GCP project** `agentic-prismv333` created and billing enabled.
- **gcloud CLI** installed and authenticated:
  ```bash
  gcloud auth login
  gcloud auth application-default login
  gcloud config set project agentic-prismv333
  ```
- **Python 3.10+** (for root and for `agentic-lens/.venv`).

---

## Step 1: Configure `versions.env`

Already set for this deployment:

- `PROJECT_ID=agentic-prismv333`
- `REGION=us-west1`
- `ADK_VERSION=1.18`
- `MODEL_VERSION=gemini-2.5-pro`

Optional: set `ORG_ID` in `versions.env` if your project is under an organization (otherwise the deploy script will try to resolve it from `gcloud projects describe`). Required for session IAM bindings after deploy.

---

## Step 2: Create virtual environments

From repo root:

```bash
# Root venv (for API / local tools)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# ADK venv (for agent deploy)
cd agentic-lens && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cd ..
```

---

## Step 3: Configure `.env` (for UI and optional local run)

```bash
cp env.example .env
```

Edit `.env` and set at least:

- `GCP_PROJECT_ID=agentic-prismv333`
- `GCP_PROJECT_NUMBER` — get with:  
  `gcloud projects describe agentic-prismv333 --format='value(projectNumber)'`
- `GCP_LOCATION=us-west1`
- `VERTEX_SEARCH_DATA_STORE_ID` — leave empty until after Step 5 if you run setup_kb; then set from script output.

---

## Step 4: Run infrastructure (`infra/apply.sh`)

From repo root:

```bash
./infra/apply.sh
```

This runs steps 01–12:

| Step | What it does |
|------|----------------|
| 01 | Enable APIs (Vertex AI, KMS, Discovery Engine, Model Armor, IAM, Secret Manager, Logging) |
| 02 | Bootstrap Agent Engine (Workload Identity Pool) |
| 03 | Secrets (e.g. github-pat-token), X-Ray IAM |
| 04 | Model Armor policies (Terraform) |
| 05 | CMEK keys (per department) — **copy printed `AGENT_ENGINE_KMS_KEY_*` into `versions.env`** |
| 06 | IAM Terraform (agent permissions) |
| 07 | Firestore Terraform |
| 08 | Telemetry (optional: `RUN_TELEMETRY=1 ./infra/apply.sh`) |
| 09 | Artifact Registry |
| 10 | Setup Knowledge Base / Events (optional: `RUN_SETUP_KB=1 ./infra/apply.sh`) — if run, put `VERTEX_SEARCH_DATA_STORE_ID` in `.env` |
| 11 | ADK patch (if `agentic-lens/.venv` exists) |
| 12 | VPC-SC perimeter (optional; set `VPC_SC_ALLOWED_USER_EMAIL` or `VPC_SC_ALLOWED_MEMBERS` if you use it) |

Important:

- After **step 05**: add the printed `AGENT_ENGINE_KMS_KEY_SUPERVISOR`, `AGENT_ENGINE_KMS_KEY_CHAT`, etc. to `versions.env`.
- If you ran **step 10**: set `VERTEX_SEARCH_DATA_STORE_ID` in `.env`.

---

## Step 5: Deploy all agents

From repo root:

```bash
./deploy.sh
```

This deploys all 12 agents to Vertex AI Agent Engine in `agentic-prismv333` / `us-west1` and, when `ORG_ID` is set (or resolved), grants session IAM roles to each engine.

- Note the **Supervisor** engine resource name from the output (e.g. `projects/.../locations/us-west1/reasoningEngines/<id>`).
- Or get it later:
  ```bash
  agentic-lens/.venv/bin/python scripts/get_agent_engine_id.py supervisor
  ```

If any agent fails (e.g. code 13): see **agentic-lens/DEPLOY.md** (quota project, APIs, permissions, logs).

---

## Step 6: Point client at Supervisor

Set the Supervisor engine for the UI (and for eng_lead’s squad, if you use it):

In `.env` (or export before deploying Glass UI):

```bash
AGENTIC_LENS_SUPERVISOR_ENGINE=projects/agentic-prismv333/locations/us-west1/reasoningEngines/<supervisor_engine_id>
```

Replace `<supervisor_engine_id>` with the ID from Step 5.

Optional (for Engineering squad): set `AGENTIC_LENS_ENGINE_SCOUT`, `AGENTIC_LENS_ENGINE_CODER`, `AGENTIC_LENS_ENGINE_QUALITY_AND_SECURITY_REVIEWER` in the same way (see **agentic-lens/DEPLOY.md**).

---

## Step 7: Deploy Glass Prism UI (optional)

To run the UI on Cloud Run:

```bash
export GCP_PROJECT_ID=agentic-prismv333
export REGION=us-west1
# Optional: so the UI uses the deployed Supervisor
export AGENTIC_LENS_SUPERVISOR_ENGINE=projects/agentic-prismv333/locations/us-west1/reasoningEngines/<id>

./deploy-glass-ui.sh
```

Service name: `ai-prism-agent-glass-ui`.  
See **PRODUCTION_CHECKLIST.md** for env vars (e.g. `GLASS_UI_LOGS_FIRESTORE_DATABASE`).

---

## Step 8: Post-deploy (telemetry, if needed)

- If you see service usage or Cloud Trace / Telemetry errors (for example, `Exception while exporting Span`) after first deploy:
  1. Ensure required APIs are enabled (one-time per project):
     ```bash
     gcloud services enable \
       telemetry.googleapis.com \
       cloudtrace.googleapis.com \
       monitoring.googleapis.com \
       logging.googleapis.com \
       --project="$PROJECT_ID"
     ```
  2. Grant tracing/monitoring/logging roles to the Agent Engine service account (one-time per project). Replace `PROJECT_NUMBER` with:
     ```bash
     gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)'
     ```
     Then:
     ```bash
     SA_EMAIL="service-PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com"

     gcloud projects add-iam-policy-binding "$PROJECT_ID" \
       --member="serviceAccount:${SA_EMAIL}" \
       --role="roles/cloudtrace.agent"

     gcloud projects add-iam-policy-binding "$PROJECT_ID" \
       --member="serviceAccount:${SA_EMAIL}" \
       --role="roles/monitoring.metricWriter"

     gcloud projects add-iam-policy-binding "$PROJECT_ID" \
       --member="serviceAccount:${SA_EMAIL}" \
       --role="roles/logging.logWriter"
     ```
  3. If you still see `serviceusage` permission issues for the engines:
     ```bash
     ./scripts/grant_service_usage_to_engines.sh
     ```
- Set quota project if you use user credentials and hit quota errors:
  ```bash
  gcloud auth application-default set-quota-project agentic-prismv333
  ```

---

## Quick reference

| Action | Command |
|--------|--------|
| Full infra | `./infra/apply.sh` |
| Deploy all agents | `./deploy.sh` |
| Deploy specific agents | `./deploy.sh supervisor eng_lead eng_scout` |
| Get Supervisor engine ID | `agentic-lens/.venv/bin/python scripts/get_agent_engine_id.py supervisor` |
| Deploy Glass UI | `GCP_PROJECT_ID=agentic-prismv333 ./deploy-glass-ui.sh` |
| Run UI locally | `uvicorn glass_ui_api:app --reload --host 0.0.0.0 --port 8000` |

---

## Docs

- **agentic-lens/DEPLOY.md** — Deploy details, CMEK, troubleshooting, cleanup.
- **PRODUCTION_CHECKLIST.md** — Production env vars, IAM, health checks, verification.
- **README_v3.md** — Architecture, departments, repo layout.
