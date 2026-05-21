# X-Ray Department — IAM bindings
# Librarian: optional Secret Manager (github-pat-token) when using a PAT; public GitHub repos need no secret. Specialist: Firestore read/write. Auditor: Firestore read-only. Manager: invoke sub-agents.

# -----------------------------------------------------------------------------
# Librarian: roles/secretmanager.secretAccessor
# Condition: only on secret projects/{project}/secrets/github-pat-token (enforced by secret-level binding).
# -----------------------------------------------------------------------------
resource "google_secret_manager_secret_iam_member" "xray_librarian_github_pat" {
  count     = (var.github_pat_secret_name != "" && local.enable_per_agent_iam) ? 1 : 0
  project   = var.project_id
  secret_id = var.github_pat_secret_name
  role      = "roles/secretmanager.secretAccessor"
  member    = local.xray_librarian_principal
}

# -----------------------------------------------------------------------------
# Specialist: roles/datastore.user — Read/Write to Knowledge Base (Firestore)
# -----------------------------------------------------------------------------
resource "google_project_iam_member" "xray_specialist_datastore_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/datastore.user"
  member  = local.xray_specialist_principal
}

# -----------------------------------------------------------------------------
# Auditor: roles/datastore.viewer — Read-Only verification of Knowledge Base
# -----------------------------------------------------------------------------
resource "google_project_iam_member" "xray_auditor_datastore_viewer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/datastore.viewer"
  member  = local.xray_auditor_principal
}

# -----------------------------------------------------------------------------
# Manager: roles/aiplatform.user — Invoke sub-agents (Librarian, Specialist, Auditor)
# -----------------------------------------------------------------------------
resource "google_project_iam_member" "xray_manager_aiplatform_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = local.xray_manager_principal
}
