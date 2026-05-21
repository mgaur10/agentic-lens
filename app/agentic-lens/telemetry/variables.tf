# Telemetry infrastructure (BigQuery + Cloud Run IAM)
# Usage: terraform init && terraform apply -var="project_id=agentic-prismv333" -var="cloud_run_service_account=..."

variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "region" {
  type        = string
  default     = "us-west1"
  description = "Region for BigQuery dataset (e.g. us-west1 or US for multi-region)"
}

# Service account that Cloud Run uses. Grant roles/bigquery.dataEditor to this SA.
# Option A (default compute SA): PROJECT_NUMBER-compute@developer.gserviceaccount.com
# Option B (custom SA): my-telemetry-writer@PROJECT_ID.iam.gserviceaccount.com
variable "cloud_run_service_account" {
  type        = string
  description = "Service account email used by Cloud Run (e.g. 123456789-compute@developer.gserviceaccount.com or custom SA)"
}
