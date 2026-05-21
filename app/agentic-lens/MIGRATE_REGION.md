# Migrating to us-east5 (from us-central1)

Default region is now **us-east5**. If you had resources in **us-central1**, destroy them there and recreate in us-east5.

## 1. Ensure config is us-east5

In repo root `versions.env`:

```bash
REGION=us-east5
```

All scripts and Terraform use this (via `source versions.env`).

## 2. Destroy us-central1 resources

### 2a. Delete Reasoning Engines (us-central1)

List and delete engines in the old region so they are not billed or counted:

```bash
# From repo root; override region for this run only
REGION=us-central1 agentic-lens/.venv/bin/python -c "
import vertexai
from vertexai.preview import reasoning_engines
vertexai.init(project='YOUR_PROJECT_ID', location='YOUR_REGION')
for e in reasoning_engines.ReasoningEngine.list():
    print('Deleting', e.resource_name)
    reasoning_engines.ReasoningEngine(e.resource_name).delete()
"
```

Or use [Vertex AI Console](https://console.cloud.google.com/vertex-ai/agent-engine) → select project → filter by region **us-central1** → delete each engine.

### 2b. Destroy Terraform (us-central1) — CMEK and Model Armor

Terraform state is per-directory; resources are regional. To destroy **us-central1** CMEK and Model Armor:

```bash
# From repo root
source versions.env
# Temporarily use old region for destroy
export REGION=us-central1

# Model Armor (security/policies)
cd agentic-lens/security/policies
terraform init
terraform destroy -var="project_id=$PROJECT_ID" -var="region=us-central1" -auto-approve

# CMEK (security/ — kms.tf)
cd ../..
cd agentic-lens/security
terraform init
terraform destroy -var="project_id=$PROJECT_ID" -var="region=us-central1" -auto-approve
```

If you already changed Terraform defaults to `us-east5`, pass the old region explicitly:

```bash
terraform destroy -var="project_id=agentic-prismv333" -var="region=us-central1" -auto-approve
```

### 2c. IAM (agent_permissions.tf)

IAM bindings are **project-level** but principal IDs can include region. If you use the same project and only changed region, you typically do **not** need to destroy IAM; just re-apply with the new region so principals point to `locations/us-east5/agents/...`. Run apply (step 3) with `REGION=us-east5`.

## 3. Create resources in us-east5

From repo root, with `REGION=us-east5` in `versions.env`:

```bash
./setup_infra.sh
./deploy.sh
```

This creates in **us-east5**:

- Agent Engine bootstrap (Workload Identity)
- Model Armor templates (security-medium, security-high)
- CMEK key ring and key
- All 8 agents (supervisor, eng_lead, eng_scout, eng_coder, eng_quality_and_security_reviewer, xray, events, chat)

## 4. Client and env vars

Point the client to us-east5 engines:

```bash
export REGION=us-east5
export AGENTIC_LENS_SUPERVISOR_ENGINE=projects/agentic-prismv333/locations/us-east5/reasoningEngines/<engine_id>
# After squad deploy, set Scout/Coder/Sentinel engine IDs for the Lead
export AGENTIC_LENS_ENGINE_SCOUT=projects/agentic-prismv333/locations/us-east5/reasoningEngines/<scout_id>
export AGENTIC_LENS_ENGINE_CODER=...
export AGENTIC_LENS_ENGINE_QUALITY_AND_SECURITY_REVIEWER=...
```

Engine IDs come from `./deploy.sh` output or the Vertex AI Agent Engine console (region **us-east5**).
