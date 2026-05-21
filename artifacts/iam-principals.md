# IAM principals reference (greenfield)

## Reasoning Engine service agent

```text
service-{PROJECT_NUMBER}@gcp-sa-aiplatform-re.iam.gserviceaccount.com
```

**Roles (post-deploy):** `roles/cloudtrace.agent`, `roles/monitoring.metricWriter`, `roles/logging.logWriter`, `roles/serviceusage.serviceUsageConsumer`  
**Script:** `migration/scripts/grant-engine-telemetry-iam.sh`

## Vertex AI service agent

```text
service-{PROJECT_NUMBER}@gcp-sa-aiplatform.iam.gserviceaccount.com
```

Granted by deploy / IAM Terraform for session and predict.

## Agent identities (12)

See `artifacts/agents-roster.md`. Terraform: `agentic-lens/security/iam/agent_permissions.tf`, `xray_permissions.tf`.

## Glass UI Cloud Run

- Runtime SA: default compute SA or custom — needs `roles/aiplatform.user`
- Optional: `roles/datastore.user` if `GLASS_UI_LOGS_FIRESTORE_DATABASE` set

## IAP

```text
service-{PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com
```

**Role on Cloud Run:** `roles/run.invoker` (set by `deploy-glass-ui.sh` when not public).

## Deployer (human / CI)

- Cloud Build Editor, Run Admin, Service Account User
- Vertex AI Admin or User
- Secret Manager Admin (PAT)
- KMS Admin (CMEK)

## Agent Gateway

Document your gateway SA in `resource-inventory.csv` — grant per org gateway guide.
