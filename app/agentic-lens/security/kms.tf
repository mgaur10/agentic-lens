# Agentic-Prism - CMEK for Vertex AI Agent Engine
# Encrypts memory and session data with a customer-managed key.
# Reference this key in engine/session_config.yaml (kms_key_id output).

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "Region for KMS key ring (same as Vertex AI Agent Engine region)"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------------------------
# Vertex AI Service Agent — required for Agent Engine to use CMEK
# Email format: service-{PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com
# (Ensure aiplatform.googleapis.com is enabled so the service agent exists.)
# ---------------------------------------------------------------------------
data "google_project" "project" {
  project_id = var.project_id
}

locals {
  vertex_ai_service_agent_email = "service-${data.google_project.project.number}@gcp-sa-aiplatform.iam.gserviceaccount.com"
}

# ---------------------------------------------------------------------------
# Key Ring
# ---------------------------------------------------------------------------
resource "google_kms_key_ring" "agentic_lens_ring" {
  name     = "agentic-lens-ring"
  location = var.region
  project  = var.project_id
}

# ---------------------------------------------------------------------------
# CryptoKey — ENCRYPT_DECRYPT, 90-day rotation
# ---------------------------------------------------------------------------
resource "google_kms_crypto_key" "agent_engine_key" {
  name            = "agent-engine-key"
  key_ring        = google_kms_key_ring.agentic_lens_ring.id
  purpose         = "ENCRYPT_DECRYPT"
  rotation_period = "7776000s" # 90 days

  lifecycle {
    prevent_destroy = false
  }
}

# ---------------------------------------------------------------------------
# Service Agent Binding — Vertex AI can encrypt/decrypt with this key
# ---------------------------------------------------------------------------
resource "google_kms_crypto_key_iam_member" "vertex_ai_encrypter_decrypter" {
  crypto_key_id = google_kms_crypto_key.agent_engine_key.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${local.vertex_ai_service_agent_email}"
}

# ---------------------------------------------------------------------------
# Outputs — reference in engine/session_config.yaml
# ---------------------------------------------------------------------------
output "kms_key_id" {
  description = "Full resource path of the CMEK; reference in engine/session_config.yaml for Agent Engine memory/session encryption."
  value       = google_kms_crypto_key.agent_engine_key.id
}

output "kms_key_ring_name" {
  description = "Key ring resource name."
  value       = google_kms_key_ring.agentic_lens_ring.name
}
