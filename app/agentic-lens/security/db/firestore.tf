# X-Ray Department — Firestore Native database (generic instance in var.region)
# Self-Learning IAM Knowledge Base uses collection `iam_knowledge_base` (created on first write).
# IAM for Specialist (datastore.user) and Auditor (datastore.viewer) is in security/iam/xray_permissions.tf.
#
# Apply from this directory: terraform init && terraform apply -var-file=../iam/terraform.tfvars
# Or: -var="project_id=..." -var="region=..."

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
}

# Enable Firestore API (required for google_firestore_database)
resource "google_project_service" "firestore" {
  project            = var.project_id
  service           = "firestore.googleapis.com"
  disable_on_destroy = false
}

# Generic Firestore Native database instance in var.region (default database for the project)
resource "google_firestore_database" "default" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.firestore]
}
