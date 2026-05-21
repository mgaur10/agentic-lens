variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "region" {
  type        = string
  description = "Default region used by the Google provider"
}

variable "bucket_name" {
  type        = string
  description = "GCS bucket name to create"
}

variable "bucket_location" {
  type        = string
  description = "GCS bucket location (e.g., us-west1)"
}

variable "force_destroy" {
  type        = bool
  description = "Whether to allow Terraform to destroy non-empty buckets"
  default     = false
}

