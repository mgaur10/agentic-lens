# Artifact Registry: Glass UI Docker image repo + IAM for Cloud Build.
# deploy-glass-ui.sh and cloudbuild_glass_ui.yaml push to us-west1-docker.pkg.dev/PROJECT_ID/prism-glass-ui/...
# The default compute SA (PROJECT_NUMBER-compute@developer.gserviceaccount.com) is used by Cloud Build
# and needs roles/artifactregistry.writer to push images.

data "google_project" "ar_project" {
  project_id = var.project_id
}

resource "google_artifact_registry_repository" "prism_glass_ui" {
  project       = var.project_id
  location      = var.artifact_registry_region
  repository_id = "prism-glass-ui"
  description   = "Docker repository for Agentic Prism Glass UI image"
  format        = "DOCKER"
}

# Cloud Build runs as the default compute SA; grant push (write) so gcloud builds submit can push the image.
resource "google_artifact_registry_repository_iam_member" "cloudbuild_writer" {
  project    = var.project_id
  location   = google_artifact_registry_repository.prism_glass_ui.location
  repository = google_artifact_registry_repository.prism_glass_ui.repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${data.google_project.ar_project.number}-compute@developer.gserviceaccount.com"
}

# Cloud Build also needs to read the uploaded source tarball from GCS (default Cloud Build bucket).
resource "google_project_iam_member" "cloudbuild_storage_object_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${data.google_project.ar_project.number}-compute@developer.gserviceaccount.com"
}

# Cloud Build logs: allow the default compute SA to write build logs.
resource "google_project_iam_member" "cloudbuild_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${data.google_project.ar_project.number}-compute@developer.gserviceaccount.com"
}
