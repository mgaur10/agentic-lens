# Agentic-Prism - Agent Identity IAM variables
# Principals are built from project_id and org_id; agent names are fixed (agentic-lens-*).

variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "org_id" {
  type        = string
  default     = ""
  description = "Google Cloud Organization ID (numeric). Required for per-agent IAM. If set, each agent gets its own bindings (agents.global.org-ORG_ID). If empty and use_project_level_principal_set is false, no agent bindings are created."
}

# Project-level principalSet is not supported in all projects (GCP may return 'unknown type'). Set true only if your project accepts it.
variable "use_project_level_principal_set" {
  type        = bool
  default     = false
  description = "If true and org_id is empty, grant agent roles via principalSet (project-level). Default false because many projects reject principalSet."
}

variable "region" {
  type        = string
  default     = "us-east5"
  description = "Region where agents are deployed (Vertex AI Agent Engine)"
}

variable "github_pat_secret_name" {
  type        = string
  default     = "github-pat-token"
  description = "Secret Manager secret name for GitHub PAT; xray_librarian gets secretAccessor. Set to \"\" to skip."
}

# Client app (Streamlit) runs Scout/Coder/Sentinel/Events with ADC — that identity needs predict.
# Option A: Set to true to grant roles/aiplatform.user to the default compute SA (Cloud Run/GCE).
# Option B: Set client_app_principal to a specific member (e.g. "user:you@example.com") instead.
variable "grant_aiplatform_to_default_compute_sa" {
  type        = bool
  default     = true
  description = "If true, grant roles/aiplatform.user to the default compute service account (used by Cloud Run / GCE). Set false if using client_app_principal."
}

# Optional: specific IAM member for the client app (overrides default compute SA if both set).
# Examples: "serviceAccount:my-backend@project.iam.gserviceaccount.com" or "user:you@example.com"
variable "client_app_principal" {
  type        = string
  default     = ""
  description = "Optional. IAM member that runs the Streamlit client. Granted roles/aiplatform.user. Leave empty to use only default compute SA (when grant_aiplatform_to_default_compute_sa is true)."
}

# Optional: developer principal for local dev (e.g. user:you@example.com). Granted reasoningEngineSessionUser
# so that when running Streamlit locally, your user can create sessions and fix 403 aiplatform.sessions.create.
variable "developer_principal" {
  type        = string
  default     = ""
  description = "Optional. IAM member for local dev (e.g. user:you@example.com). Granted reasoningEngineSessionUser so ADC can create Agent Engine sessions. Leave empty to skip."
}

# Optional: principals discovered from 403 logs (e.g. from scripts/fetch_session_403_principal.py).
# Each gets reasoningEngineSessionUser. Use when the denied principal is not covered by developer_principal or default compute SA.
variable "additional_session_principals" {
  type        = list(string)
  default     = []
  description = "Optional. List of IAM members (e.g. [\"user:foo@example.com\", \"serviceAccount:...\"]) to grant reasoningEngineSessionUser. Add the principal printed by fetch_session_403_principal.py here, then terraform apply."
}

# Artifact Registry for Glass UI image (Cloud Build push). Must match cloudbuild_glass_ui.yaml (us-west1).
variable "artifact_registry_region" {
  type        = string
  default     = "us-west1"
  description = "Region for Artifact Registry repo prism-glass-ui (Glass UI Docker image)."
}
