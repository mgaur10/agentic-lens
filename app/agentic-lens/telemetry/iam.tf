# Grant Cloud Run service account BigQuery Data Editor for streaming inserts
# (no manual key management; uses Workload Identity / default ADC in Cloud Run)

resource "google_project_iam_member" "cloud_run_bigquery_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${var.cloud_run_service_account}"
}
