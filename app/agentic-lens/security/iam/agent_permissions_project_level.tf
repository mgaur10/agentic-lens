# When org_id is empty and use_project_level_principal_set is true: grant at project level via principalSet.
# Note: principalSet is rejected in many projects (400 "unknown type"). Prefer setting org_id for per-agent IAM.
# Format: principalSet://agents.global.project-PROJECT_NUMBER.system.id.goog/attribute.platformContainer/aiplatform/projects/PROJECT_NUMBER

locals {
  project_level_principal_set = "principalSet://agents.global.project-${data.google_project.project.number}.system.id.goog/attribute.platformContainer/aiplatform/projects/${data.google_project.project.number}"
  use_project_level_iam      = var.org_id == "" && var.use_project_level_principal_set
}

# Base roles for all agents in the project (when not using org-level per-agent bindings)
resource "google_project_iam_member" "project_level_agents_log_writer" {
  count   = local.use_project_level_iam ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = local.project_level_principal_set
}
resource "google_project_iam_member" "project_level_agents_service_usage" {
  count   = local.use_project_level_iam ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.project_level_principal_set
}
resource "google_project_iam_member" "project_level_agents_cloudtrace" {
  count   = local.use_project_level_iam ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = local.project_level_principal_set
}
resource "google_project_iam_member" "project_level_agents_aiplatform_user" {
  count   = local.use_project_level_iam ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = local.project_level_principal_set
}
resource "google_project_iam_member" "project_level_agents_reasoning_engine_session_user" {
  count   = local.use_project_level_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.project_level_principal_set
}
resource "google_project_iam_member" "project_level_agents_aiplatform_admin" {
  count   = local.use_project_level_iam ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.admin"
  member  = local.project_level_principal_set
}
