# Enable APIs for Agentic-Prism (new project)

For a **new project**, enable these Google Cloud APIs before running Terraform or deploying agents.

## Quick: run the script

From the repo root (or from `agentic-lens/`):

```bash
# From ai-agent-prism-v2-adk/
./agentic-lens/scripts/enable-apis.sh agentic-prismv333

# Or set project and run from agentic-lens/
export GOOGLE_CLOUD_PROJECT=agentic-prismv333
./scripts/enable-apis.sh
```

## APIs enabled

| API | Purpose |
|-----|--------|
| `aiplatform.googleapis.com` | Vertex AI / Agent Engine, Gemini |
| `telemetry.googleapis.com` | Agent Engine tracing / OpenTelemetry export |
| `modelarmor.googleapis.com` | Model Armor templates (security-medium, security-high) |
| `dlp.googleapis.com` | Cloud DLP (SDP redaction in Model Armor) |
| `discoveryengine.googleapis.com` | Discovery Engine / Vertex Search (Events agent) |
| `cloudresourcemanager.googleapis.com` | Project and resource metadata |
| `cloudasset.googleapis.com` | Cloud Asset (X-Ray agent — roles/cloudasset.viewer) |
| `iam.googleapis.com` | IAM (Agent Identity bindings, custom roles) |
| `storage.googleapis.com` | Cloud Storage (Vertex staging, etc.) |
| `compute.googleapis.com` | Compute (often required by Vertex) |

## Manual: gcloud commands

```bash
export PROJECT_ID=agentic-prismv333

gcloud services enable \
  aiplatform.googleapis.com \
  telemetry.googleapis.com \
  modelarmor.googleapis.com \
  dlp.googleapis.com \
  discoveryengine.googleapis.com \
  cloudresourcemanager.googleapis.com \
  cloudasset.googleapis.com \
  iam.googleapis.com \
  storage.googleapis.com \
  compute.googleapis.com \
  --project="$PROJECT_ID"
```

## Console

1. Open [APIs & Services → Library](https://console.cloud.google.com/apis/library).
2. Select project **agentic-prismv333** (or your project).
3. Search for each API above and click **Enable**.

## After enabling

1. **Model Armor (Terraform):**  
   `cd agentic-lens/security/policies && terraform init && terraform apply -var="project_id=agentic-prismv333" -var="region=us-central1"`

2. **Agent Identity IAM (Terraform):**  
   `cd agentic-lens/security/iam && terraform init && terraform apply -var="project_id=agentic-prismv333" -var="org_id=YOUR_ORG_ID"`

3. **Auth:**  
   `gcloud auth login` and `gcloud auth application-default login` so Terraform and the app can call these APIs.
