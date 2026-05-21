resource "google_storage_bucket" "ingest_bucket" {
  name     = var.bucket_name
  location = var.bucket_location

  # We keep this bucket private. Users can still upload in the GCP Console
  # once IAM is granted later.
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  force_destroy = var.force_destroy

  versioning {
    enabled = false
  }
}

