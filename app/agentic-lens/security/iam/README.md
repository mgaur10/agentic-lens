# Agent Identity IAM (Terraform) — Least Privilege

Grants roles to all **12** Agent Identity principals (`principal://.../agents/agentic_lens_{name}`). Agent names use underscores (e.g. `agentic_lens_supervisor`, `eng_lead`, `xray_manager`).

## Layers

| Layer | Role | Members |
|-------|------|---------|
| **Base** | `roles/logging.logWriter` | All 12 agents |
| **Orchestration** | `roles/aiplatform.user` | agentic_lens_supervisor, chat, eng_lead, xray_manager |
| **Operational** | Secret (optional): `roles/secretmanager.secretAccessor` on `github-pat-token` if you use a PAT | xray_librarian |
| | `roles/discoveryengine.viewer` (Vertex Search) | events |
| | `roles/viewer` (read-only project) | eng_scout, xray_architect |
| **Security (SDP)** | `roles/dlp.user` | eng_quality_and_security_reviewer, xray_auditor |
| **Security (Model Armor)** | `roles/modelarmor.admin` | xray_manager |
| | `roles/aiplatform.viewer` (safety alerts) | agentic_lens_supervisor |
| | `roles/modelarmor.user` (Model Armor API) | agentic_lens_supervisor |
| **Reasoning Engine sessions** | Custom `reasoningEngineSessionUser` (`aiplatform.sessions.create`, `.get`, `.list`) | agentic_lens_supervisor |

The custom role fixes **403 PERMISSION_DENIED: Permission 'aiplatform.sessions.create' denied** when the Supervisor (root Reasoning Engine) creates sessions for `stream_query`. `roles/aiplatform.user` does not include session create.

Set `github_pat_secret_name = ""` in `terraform.tfvars` to skip secret access if the secret does not exist.

**Client app (Streamlit):** Scout/Coder/Sentinel/Events in the UI call Vertex AI with **Application Default Credentials** (not agent identity). The 403 `aiplatform.endpoints.predict` in the UI is fixed by granting **roles/aiplatform.user** to whoever runs the app:
- **Cloud Run / GCE:** set `grant_aiplatform_to_default_compute_sa = true` (default) so the default compute service account gets the role.
- **Local dev:** your user needs the role — in Console add your user to the project with role **Vertex AI User**, or set `client_app_principal = "user:YOUR_EMAIL"` and apply.

## Prerequisites

**The Workload Identity Pool must exist before applying.**  
Google creates it when Vertex AI Agent Engine (AGENT_IDENTITY) is first used in the project—typically on the first `adk deploy`. If you see:

```text
Identity Pool does not exist (organizations/.../workloadIdentityPools/agents.global.org-....system.id.goog)
```

then run **`adk deploy`** (or `./deploy.sh`) once from the ADK project root, then run `terraform apply` here.

## Usage

1. Copy `terraform.tfvars.example` to `terraform.tfvars` and set `project_id` and `org_id`.
2. Ensure the Agent Identity pool exists (deploy agents once if needed).
3. `terraform init && terraform apply -auto-approve`
