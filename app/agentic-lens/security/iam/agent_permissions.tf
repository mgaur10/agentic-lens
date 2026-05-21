# Agentic-Prism - Agent Identity IAM (Least Privilege)
# Grants roles to Agent Identity principals (no google_service_account).
# Trust domain: with org use agents.global.org-{ORG_ID}.system.id.goog;
# without org use agents.global.project-{PROJECT_NUMBER}.system.id.goog (project-level).
# Path: .../resources/aiplatform/projects/{PROJECT}/locations/{REGION}/agents/agentic_lens_{NAME}
#
# LAYERS:
# 1. Base (all 12): roles/logging.logWriter, roles/serviceusage.serviceUsageConsumer, roles/cloudtrace.agent
# 2. Orchestration (Brains): supervisor, chat, eng_lead, xray_manager -> roles/aiplatform.user
# 3. Operational: xray_librarian (secretAccessor), events (Discovery Engine viewer), eng_scout/xray_architect (Viewer)
# 4. Security: SDP (dlp.user), Model Armor (modelarmor.admin + aiplatform.viewer for alerts)

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Project data needed for project-level trust domain when org_id is empty
data "google_project" "project" {
  project_id = var.project_id
}

locals {
  # With org: agents.global.org-ORG_ID; without org use principalSet in agent_permissions_project_level.tf (per-agent principal can be "unknown type" in some projects)
  trust_domain           = "agents.global.org-${var.org_id}.system.id.goog"
  base_path              = "principal://${local.trust_domain}/resources/aiplatform/projects/${var.project_id}/locations/${var.region}/agents"
  enable_per_agent_iam   = var.org_id != "" # when org_id set: per-agent bindings; when empty: project-level principalSet bindings only
  # All 12 Vertex AI Agent identities (underscore naming)
  supervisor_principal    = "${local.base_path}/agentic_lens_supervisor"
  # Legacy hyphen principal: existing Reasoning Engines may still use this identity for session create.
  # Grant same session/admin so 403 aiplatform.sessions.create is fixed regardless of which identity Vertex uses.
  supervisor_principal_legacy = "${local.base_path}/agentic-lens-supervisor"
  chat_principal          = "${local.base_path}/agentic_lens_chat"
  chat_principal_legacy   = "${local.base_path}/agentic-lens-chat"
  events_principal       = "${local.base_path}/agentic_lens_events"
  eng_lead_principal     = "${local.base_path}/agentic_lens_eng_lead"
  eng_scout_principal    = "${local.base_path}/agentic_lens_eng_scout"
  eng_coder_principal    = "${local.base_path}/agentic_lens_eng_coder"
  eng_quality_and_security_reviewer_principal = "${local.base_path}/agentic_lens_eng_quality_and_security_reviewer"
  xray_manager_principal = "${local.base_path}/agentic_lens_xray_manager"
  xray_librarian_principal = "${local.base_path}/agentic_lens_xray_librarian"
  xray_architect_principal = "${local.base_path}/agentic_lens_xray_architect"
  xray_specialist_principal = "${local.base_path}/agentic_lens_xray_specialist"
  xray_auditor_principal = "${local.base_path}/agentic_lens_xray_auditor"

  all_agent_principals = [
    local.supervisor_principal,
    local.chat_principal,
    local.events_principal,
    local.eng_lead_principal,
    local.eng_scout_principal,
    local.eng_coder_principal,
    local.eng_quality_and_security_reviewer_principal,
    local.xray_manager_principal,
    local.xray_librarian_principal,
    local.xray_architect_principal,
    local.xray_specialist_principal,
    local.xray_auditor_principal,
  ]
}

# =============================================================================
# 1. BASE PERMISSION (All 12 agents)
# roles/logging.logWriter, roles/serviceusage.serviceUsageConsumer
# =============================================================================
resource "google_project_iam_member" "supervisor_log_writer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = local.supervisor_principal
}
resource "google_project_iam_member" "chat_log_writer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = local.chat_principal
}
resource "google_project_iam_member" "events_log_writer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = local.events_principal
}
resource "google_project_iam_member" "eng_lead_log_writer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = local.eng_lead_principal
}
resource "google_project_iam_member" "eng_scout_log_writer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = local.eng_scout_principal
}
resource "google_project_iam_member" "eng_coder_log_writer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = local.eng_coder_principal
}
resource "google_project_iam_member" "eng_quality_and_security_reviewer_log_writer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = local.eng_quality_and_security_reviewer_principal
}
resource "google_project_iam_member" "xray_manager_log_writer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = local.xray_manager_principal
}
resource "google_project_iam_member" "xray_librarian_log_writer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = local.xray_librarian_principal
}
resource "google_project_iam_member" "xray_architect_log_writer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = local.xray_architect_principal
}
resource "google_project_iam_member" "xray_specialist_log_writer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = local.xray_specialist_principal
}
resource "google_project_iam_member" "xray_auditor_log_writer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = local.xray_auditor_principal
}

# roles/serviceusage.serviceUsageConsumer — use enabled APIs (all 12 agents)
resource "google_project_iam_member" "supervisor_service_usage_consumer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.supervisor_principal
}
resource "google_project_iam_member" "chat_service_usage_consumer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.chat_principal
}
resource "google_project_iam_member" "events_service_usage_consumer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.events_principal
}
resource "google_project_iam_member" "eng_lead_service_usage_consumer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.eng_lead_principal
}
resource "google_project_iam_member" "eng_scout_service_usage_consumer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.eng_scout_principal
}
resource "google_project_iam_member" "eng_coder_service_usage_consumer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.eng_coder_principal
}
resource "google_project_iam_member" "eng_quality_and_security_reviewer_service_usage_consumer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.eng_quality_and_security_reviewer_principal
}
resource "google_project_iam_member" "xray_manager_service_usage_consumer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.xray_manager_principal
}
resource "google_project_iam_member" "xray_librarian_service_usage_consumer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.xray_librarian_principal
}
resource "google_project_iam_member" "xray_architect_service_usage_consumer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.xray_architect_principal
}
resource "google_project_iam_member" "xray_specialist_service_usage_consumer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.xray_specialist_principal
}
resource "google_project_iam_member" "xray_auditor_service_usage_consumer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = local.xray_auditor_principal
}

# roles/cloudtrace.agent — telemetry.traces.write for Vertex AI Reasoning Engine tracing (all 12 agents)
resource "google_project_iam_member" "supervisor_cloudtrace_agent" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = local.supervisor_principal
}
resource "google_project_iam_member" "chat_cloudtrace_agent" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = local.chat_principal
}
resource "google_project_iam_member" "events_cloudtrace_agent" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = local.events_principal
}
resource "google_project_iam_member" "eng_lead_cloudtrace_agent" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = local.eng_lead_principal
}
resource "google_project_iam_member" "eng_scout_cloudtrace_agent" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = local.eng_scout_principal
}
resource "google_project_iam_member" "eng_coder_cloudtrace_agent" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = local.eng_coder_principal
}
resource "google_project_iam_member" "eng_quality_and_security_reviewer_cloudtrace_agent" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = local.eng_quality_and_security_reviewer_principal
}
resource "google_project_iam_member" "xray_manager_cloudtrace_agent" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = local.xray_manager_principal
}
resource "google_project_iam_member" "xray_librarian_cloudtrace_agent" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = local.xray_librarian_principal
}
resource "google_project_iam_member" "xray_architect_cloudtrace_agent" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = local.xray_architect_principal
}
resource "google_project_iam_member" "xray_specialist_cloudtrace_agent" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = local.xray_specialist_principal
}
resource "google_project_iam_member" "xray_auditor_cloudtrace_agent" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = local.xray_auditor_principal
}

# =============================================================================
# 2. ORCHESTRATION LAYER (The Brains) — Invoke other agents
# roles/aiplatform.user — invoke agents + aiplatform.endpoints.predict (Gemini)
# Members: supervisor, chat, eng_lead (xray_manager is in xray_permissions.tf)
# =============================================================================
resource "google_project_iam_member" "supervisor_aiplatform_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = local.supervisor_principal
}
resource "google_project_iam_member" "chat_aiplatform_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = local.chat_principal
}
resource "google_project_iam_member" "eng_lead_aiplatform_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = local.eng_lead_principal
}

# Events concierge uses Vertex AI RAG (Managed RAG Corpus retrieval).
# Grant Vertex AI user permissions to allow `rag.retrieval_query` calls.
resource "google_project_iam_member" "events_aiplatform_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = local.events_principal
}

# 2b. OPERATIONAL AGENTS — Need Gemini predict when serving (invoked by lead)
# roles/aiplatform.user — aiplatform.endpoints.predict for model inference
# Members: eng_scout, eng_coder, eng_quality_and_security_reviewer
# =============================================================================
resource "google_project_iam_member" "eng_scout_aiplatform_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = local.eng_scout_principal
}
resource "google_project_iam_member" "eng_coder_aiplatform_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = local.eng_coder_principal
}
resource "google_project_iam_member" "eng_quality_and_security_reviewer_aiplatform_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = local.eng_quality_and_security_reviewer_principal
}

# =============================================================================
# 3. OPERATIONAL LAYER (The Hands)
# X-Ray Librarian secret access is in xray_permissions.tf.
# =============================================================================

# 3a. Knowledge Access — events -> Vertex Search (Discovery Engine)
resource "google_project_iam_member" "events_discoveryengine_viewer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/discoveryengine.viewer"
  member  = local.events_principal
}

# 3b. Infrastructure View — eng_scout, xray_architect (read-only project state)
resource "google_project_iam_member" "eng_scout_viewer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/viewer"
  member  = local.eng_scout_principal
}
resource "google_project_iam_member" "xray_architect_viewer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/viewer"
  member  = local.xray_architect_principal
}

# =============================================================================
# 4. SECURITY & COMPLIANCE (Model Armor + SDP) — CRITICAL
# =============================================================================

# 4a. Sensitive Data Protection (SDP) — Inspect content for PII/Secrets
# roles/dlp.user — eng_quality_and_security_reviewer (code), xray_auditor (IAM risky bindings)
resource "google_project_iam_member" "eng_quality_and_security_reviewer_dlp_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/dlp.user"
  member  = local.eng_quality_and_security_reviewer_principal
}
resource "google_project_iam_member" "xray_auditor_dlp_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/dlp.user"
  member  = local.xray_auditor_principal
}

# 4b. Model Armor — Manage/View safety policies (Security Lead)
# roles/modelarmor.admin — xray_manager (GCP uses modelarmor.* not aiplatform.modelArmorAdmin)
resource "google_project_iam_member" "xray_manager_modelarmor_admin" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/modelarmor.admin"
  member  = local.xray_manager_principal
}

# 4c. View safety alerts/logs — supervisor (know if a prompt was blocked)
resource "google_project_iam_member" "supervisor_aiplatform_viewer" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.viewer"
  member  = local.supervisor_principal
}

# 4d. Model Armor API — supervisor runs security gate (sanitize_user_prompt)
# roles/modelarmor.user — call Model Armor API (modelarmor.{region}.rep.googleapis.com)
resource "google_project_iam_member" "supervisor_modelarmor_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/modelarmor.user"
  member  = local.supervisor_principal
}

# 4e. Reasoning Engine sessions — Supervisor (root engine) must create/use sessions and session events
# 403 PERMISSION_DENIED: aiplatform.sessions.create / aiplatform.sessionEvents.list on resource
#   'projects/.../reasoningEngines/.../sessions/...'. roles/aiplatform.user does not include them.
resource "google_project_iam_custom_role" "reasoning_engine_session_user" {
  role_id     = "reasoningEngineSessionUser"
  title       = "Reasoning Engine Session User"
  description = "Create and use Vertex AI Reasoning Engine / Agent Engine sessions and session events."
  permissions = [
    "aiplatform.sessions.create",
    "aiplatform.sessions.get",
    "aiplatform.sessions.list",
    "aiplatform.sessionEvents.list",
    "aiplatform.sessionEvents.append",
  ]
}
resource "google_project_iam_member" "supervisor_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.supervisor_principal
}
resource "google_project_iam_member" "chat_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.chat_principal
}
resource "google_project_iam_member" "chat_legacy_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.chat_principal_legacy
}

# Session user for all department agents (so they can create/use sessions when invoked)
resource "google_project_iam_member" "events_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.events_principal
}
resource "google_project_iam_member" "eng_lead_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.eng_lead_principal
}
resource "google_project_iam_member" "eng_scout_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.eng_scout_principal
}
resource "google_project_iam_member" "eng_coder_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.eng_coder_principal
}
resource "google_project_iam_member" "eng_quality_and_security_reviewer_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.eng_quality_and_security_reviewer_principal
}
resource "google_project_iam_member" "xray_manager_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.xray_manager_principal
}
resource "google_project_iam_member" "xray_librarian_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.xray_librarian_principal
}
resource "google_project_iam_member" "xray_architect_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.xray_architect_principal
}
resource "google_project_iam_member" "xray_specialist_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.xray_specialist_principal
}
resource "google_project_iam_member" "xray_auditor_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.xray_auditor_principal
}

resource "google_project_iam_member" "chat_datastore_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/datastore.user"
  member  = local.chat_principal
}
resource "google_project_iam_member" "chat_legacy_datastore_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/datastore.user"
  member  = local.chat_principal_legacy
}

# Legacy hyphen principal: if Reasoning Engine was created with identity agentic-lens-supervisor,
# Vertex still uses that principal for session create. Grant same roles so 403 is resolved.
resource "google_project_iam_member" "supervisor_legacy_reasoning_engine_session_user" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = local.supervisor_principal_legacy
}
resource "google_project_iam_member" "supervisor_legacy_aiplatform_admin" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.admin"
  member  = local.supervisor_principal_legacy
}

# =============================================================================
# 5. CLIENT APP (Streamlit backend) — Scout/Coder/Sentinel/Events use ADC
# The UI backend (engineering.py, events.py, etc.) calls Vertex AI with Application
# Default Credentials, NOT agent identity. Grant predict to whoever runs the app.
# =============================================================================

# Default compute SA (Cloud Run / GCE default) — often used when running the Streamlit app
resource "google_project_iam_member" "client_app_default_compute_sa_aiplatform_user" {
  count   = var.grant_aiplatform_to_default_compute_sa ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# Model Armor scan runs in the backend (before sending to Supervisor) — Cloud Run SA needs modelarmor.user
resource "google_project_iam_member" "client_app_default_compute_sa_modelarmor_user" {
  count   = var.grant_aiplatform_to_default_compute_sa ? 1 : 0
  project = var.project_id
  role    = "roles/modelarmor.user"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# Reasoning Engine runtime may use default compute SA for session create — grant session role so
# 403 PERMISSION_DENIED aiplatform.sessions.create is resolved regardless of which identity is used.
resource "google_project_iam_member" "default_compute_sa_reasoning_engine_session_user" {
  count   = var.grant_aiplatform_to_default_compute_sa ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

#
# Google-managed service agents used by Vertex AI / Reasoning Engine runtimes
# ---------------------------------------------------------------------------
# 1) AI Platform Reasoning Engine Service Agent
#    service-PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com
#    Used by the Reasoning Engine runtime itself.
# 2) Vertex AI Service Agent (generic Vertex AI)
#    service-PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com
#    Used by Vertex AI backend services; the ADK sessions library may call
#    aiplatform.sessions.create as this service agent on behalf of the engine.
# Grant both service agents the session custom role + aiplatform.admin so that
# any runtime or backend component invoking sessions.create has permission.
# See:
#   - https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/manage/access
#   - https://cloud.google.com/vertex-ai/docs/general/custom-service-account#service-agents

resource "google_project_iam_member" "reasoning_engine_sa_session_user" {
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
}

# Allow the Reasoning Engine service agent to manage and serve Reasoning Engines.
resource "google_project_iam_member" "reasoning_engine_sa_service_role" {
  project = var.project_id
  role    = "roles/aiplatform.reasoningEngineServiceAgent"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "reasoning_engine_sa_aiplatform_admin" {
  project = var.project_id
  role    = "roles/aiplatform.admin"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
}

# Allow the Reasoning Engine service agent to call publisher models (endpoints.predict).
resource "google_project_iam_member" "reasoning_engine_sa_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-aiplatform-re.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "vertex_ai_sa_reasoning_engine_session_user" {
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-aiplatform.iam.gserviceaccount.com"
}
resource "google_project_iam_member" "vertex_ai_sa_aiplatform_admin" {
  project = var.project_id
  role    = "roles/aiplatform.admin"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-aiplatform.iam.gserviceaccount.com"
}

# Allow the generic Vertex AI service agent to call publisher models (endpoints.predict) on behalf of engines.
resource "google_project_iam_member" "vertex_ai_sa_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-aiplatform.iam.gserviceaccount.com"
}

# 4f. Fallback: roles/aiplatform.admin for session create when custom role was insufficient.
# Vertex AI Administrator includes aiplatform.* (covers aiplatform.sessions.create). Grant to
# both Supervisor (agent identity) and default compute SA so whichever identity the Reasoning
# Engine uses for session create has permission.
resource "google_project_iam_member" "supervisor_aiplatform_admin" {
  count   = local.enable_per_agent_iam ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.admin"
  member  = local.supervisor_principal
}
resource "google_project_iam_member" "default_compute_sa_aiplatform_admin" {
  count   = var.grant_aiplatform_to_default_compute_sa ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.admin"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# Optional: explicit client app principal (e.g. custom SA or user for local dev)
resource "google_project_iam_member" "client_app_aiplatform_user" {
  count   = var.client_app_principal != "" ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = var.client_app_principal
}

# Optional: developer principal for local dev — grant session role so stream_query can create sessions.
# Set developer_principal = "user:your.email@example.com" in terraform.tfvars to fix 403 when running Streamlit locally.
resource "google_project_iam_member" "developer_reasoning_engine_session_user" {
  count   = var.developer_principal != "" ? 1 : 0
  project = var.project_id
  role    = google_project_iam_custom_role.reasoning_engine_session_user.id
  member  = var.developer_principal
}
resource "google_project_iam_member" "developer_aiplatform_user" {
  count   = var.developer_principal != "" ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = var.developer_principal
}

# Principals discovered from 403 logs (fetch_session_403_principal.py) — grant session role so 403 is resolved.
resource "google_project_iam_member" "additional_session_principal" {
  for_each = toset(var.additional_session_principals)
  project  = var.project_id
  role     = google_project_iam_custom_role.reasoning_engine_session_user.id
  member   = each.value
}
