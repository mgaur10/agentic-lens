output "bucket_name" {
  value       = google_storage_bucket.ingest_bucket.name
  description = "Name of the created ingest bucket"
}

output "bucket_url" {
  value       = "gs://${google_storage_bucket.ingest_bucket.name}"
  description = "gs:// URL of the created ingest bucket"
}

