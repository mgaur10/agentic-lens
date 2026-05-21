# BigQuery backend for application telemetry
# Dataset: prism_telemetry
# Table: demo_usage_logs (timestamp, usage_type, user_email, customer_name, opportunity_link)

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

resource "google_bigquery_dataset" "prism_telemetry" {
  project    = var.project_id
  dataset_id = "prism_telemetry"
  location   = var.region
  description = "Application telemetry for Prism (demo usage, etc.)"
}

resource "google_bigquery_table" "demo_usage_logs" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.prism_telemetry.dataset_id
  table_id   = "demo_usage_logs"
  description = "Demo usage and application telemetry logs"

  schema = jsonencode([
    {
      name = "timestamp"
      type = "TIMESTAMP"
      mode = "REQUIRED"
    },
    {
      name = "usage_type"
      type = "STRING"
      mode = "REQUIRED"
    },
    {
      name = "user_email"
      type = "STRING"
      mode = "REQUIRED"
    },
    {
      name = "customer_name"
      type = "STRING"
      mode = "NULLABLE"
    },
    {
      name = "opportunity_link"
      type = "STRING"
      mode = "NULLABLE"
    }
  ])
}
