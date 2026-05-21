# Agent identity vs IAM principal verification

When using **AGENT_IDENTITY** (per-agent managed identity), the identity Vertex AI assigns at runtime **must match** the principal we grant in Terraform. A mismatch caused earlier "Failed to create session" / 403 errors.

## Format

- **Vertex AI Agent Identity (runtime):**  
  `principal://agents.global.org-{ORG_ID}.system.id.goog/resources/aiplatform/projects/{PROJECT_ID}/locations/{REGION}/agents/{AGENT_NAME}`

- **Agent name** comes from:
  - **adk.yaml** `name` for each agent (and from `agent.yaml` / `root_agent.yaml` when loaded by ADK).
  - Must use **underscores** (project standard); no hyphens.

- **Terraform principal** in `agent_permissions.tf`:  
  `local.base_path` + `"/" + agent_identity_name`  
  where `agent_identity_name` is the **same** as the agent name for non-supervisor, and `agentic_lens_supervisor` for the root.

## Supervisor (critical)

| Source | Value |
|--------|--------|
| **adk.yaml** `name` | `agentic_lens_supervisor` |
| **agent.yaml** / **root_agent.yaml** `name` | `agentic_lens_supervisor` |
| **agent.py** default (if name missing) | `agentic_lens_supervisor` |
| **Terraform** `supervisor_principal` | `.../agents/agentic_lens_supervisor` |

**Result:** Supervisor runtime identity and IAM principal both use `agentic_lens_supervisor` → **aligned**.

## All 12 agents (config name → IAM principal suffix)

| Agent | adk.yaml / agent name | Terraform principal suffix |
|-------|------------------------|----------------------------|
| Supervisor | `agentic_lens_supervisor` | `agentic_lens_supervisor` |
| Chat | `chat` | `agentic_lens_chat` |
| Events | `events` | `agentic_lens_events` |
| eng_lead | `eng_lead` | `agentic_lens_eng_lead` |
| eng_scout | `eng_scout` | `agentic_lens_eng_scout` |
| eng_coder | `eng_coder` | `agentic_lens_eng_coder` |
| eng_quality_and_security_reviewer | `eng_quality_and_security_reviewer` | `agentic_lens_eng_quality_and_security_reviewer` |
| xray_manager | `xray_manager` | `agentic_lens_xray_manager` |
| xray_librarian | `xray_librarian` | `agentic_lens_xray_librarian` |
| xray_architect | `xray_architect` | `agentic_lens_xray_architect` |
| xray_specialist | `xray_specialist` | `agentic_lens_xray_specialist` |
| xray_auditor | `xray_auditor` | `agentic_lens_xray_auditor` |

**Note:** For most agents the principal suffix is `agentic_lens_` + adk name (e.g. `eng_lead` → `agentic_lens_eng_lead`). The Supervisor is the root and uses the full name `agentic_lens_supervisor` in both config and IAM.

## How to verify in GCP

1. **Deployed agent identity:** After deploy, in Vertex AI → Reasoning Engines (or Agent Engine), open the Supervisor engine and check its identity / principal if shown.
2. **IAM:** Cloud Console → IAM & Admin → IAM. Search for `agentic_lens_supervisor` or the project; confirm bindings for `principal://agents.global.../agents/agentic_lens_supervisor` have the expected roles (e.g. `roles/aiplatform.user`, `roles/logging.logWriter`, session user, Model Armor, etc.).

**403 aiplatform.sessions.create:** If the error persists, the Reasoning Engine may still be using the **legacy hyphen** principal (`agentic-lens-supervisor`). Terraform grants session + admin to **both**:
- `agentic_lens_supervisor` (current)
- `agentic-lens-supervisor` (legacy)

So whichever identity Vertex uses for session create has permission. Ensure `terraform apply` has been run so these bindings exist in the project.
