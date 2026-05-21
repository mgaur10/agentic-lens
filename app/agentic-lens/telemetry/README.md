# Telemetry infrastructure (BigQuery + Cloud Run IAM)

Provisions:

- **BigQuery dataset** `prism_telemetry`
- **BigQuery table** `demo_usage_logs` with schema:
  - `timestamp` (TIMESTAMP, REQUIRED)
  - `usage_type` (STRING, REQUIRED)
  - `user_email` (STRING, REQUIRED)
  - `customer_name` (STRING, NULLABLE)
  - `opportunity_link` (STRING, NULLABLE)
- **IAM**: `roles/bigquery.dataEditor` on the project for the Cloud Run service account (stream inserts without manual keys).

## Option 1: Terraform

```bash
cd agentic-lens/telemetry
terraform init
terraform apply \
  -var="project_id=agentic-prismv333" \
  -var="cloud_run_service_account=YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com"
```

To use the default compute SA, resolve the email first:

```bash
PROJECT_NUMBER=$(gcloud projects describe agentic-prismv333 --format='value(projectNumber)')
terraform apply \
  -var="project_id=agentic-prismv333" \
  -var="cloud_run_service_account=${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
```

## Option 2: gcloud + bq

From repo root:

```bash
GCP_PROJECT_ID=agentic-prismv333 REGION=us-west1 ./agentic-lens/scripts/provision-telemetry-gcloud.sh
```

If Cloud Run uses a custom service account:

```bash
GCP_PROJECT_ID=agentic-prismv333 CLOUD_RUN_SA=my-app@agentic-prismv333.iam.gserviceaccount.com ./agentic-lens/scripts/provision-telemetry-gcloud.sh
```

Omitting `CLOUD_RUN_SA` uses the default compute service account.
