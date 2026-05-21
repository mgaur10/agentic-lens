# Firestore (X-Ray Knowledge Base) — generic database in var.region
# IAM bindings for Specialist/Auditor are in security/iam/xray_permissions.tf.

variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "region" {
  type        = string
  default     = "us-west1"
  description = "Region for Firestore database (e.g. us-west1). Use same as Agent Engine region."
}
