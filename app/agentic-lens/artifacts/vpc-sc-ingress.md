# VPC Service Controls — ingress for Agent Engine deploy

If the project is inside a **VPC-SC perimeter** (org or repo step 12), Reasoning Engine deploy/start often fails without access to Storage and Artifact Registry.

## Service accounts to allow

| Principal | Purpose |
|-----------|---------|
| `service-PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com` | Reasoning Engine runtime |
| `service-PROJECT_NUMBER@gcp-sa-aiplatform.iam.gserviceaccount.com` | Vertex AI |
| Cloud Build / deployer SA | Build and push images |
| Glass UI Cloud Run SA | Runtime |
| Agent Gateway SA | Per org setup |

## Restricted services (minimum for deploy)

- `storage.googleapis.com`
- `artifactregistry.googleapis.com`
- `aiplatform.googleapis.com`

See `agentic-lens/DEPLOY.md` troubleshooting.

## Repo VPC-SC

- Terraform: `agentic-lens/security/vpc_sc/`
- Step: `./infra/apply.sh 12 12` with `VPC_SC_ALLOWED_USER_EMAIL` or `VPC_SC_ALLOWED_MEMBERS`

**If org already has a perimeter:** set `SKIP_INFRA_VPC_SC=1` and ask security to add the project + SA ingress to the existing perimeter.

## Verification

```bash
# Deploy one agent after perimeter update
./deploy.sh supervisor
```

Check Logs Explorer for VPC-SC denied errors.
