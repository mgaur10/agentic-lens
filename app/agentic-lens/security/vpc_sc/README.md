# VPC Service Controls (VPC-SC) and Access Context Manager

This Terraform creates:

1. **Access Context Manager policy** (org-level) — container for access levels and perimeters.
2. **Access level** — identities (users or service accounts) allowed to ingress and egress the perimeter.
3. **Service perimeter** — protects the project; only requests from the access level can cross the boundary.

## Prerequisites

- Project must be under an **organization** (ORG_ID set).
- Enable API: `gcloud services enable accesscontextmanager.googleapis.com --project=PROJECT_ID`
- You need **Organization Admin** or **Access Context Manager Admin** to create the policy (org-level).

## Variables

| Variable | Description |
|----------|-------------|
| `project_id` | GCP project to protect |
| `org_id` | Organization ID (parent of the project) |
| `allowed_members` | List of members allowed ingress/egress, e.g. `["user:dev@example.com"]` |

Set via `-var`, `terraform.tfvars`, or env (e.g. `TF_VAR_allowed_members`).

## Run

From repo root, step 12 of `./infra/apply.sh` runs this Terraform with:

- `project_id`, `org_id` from `versions.env`
- `allowed_members` from env `VPC_SC_ALLOWED_USER_EMAIL` (single user, formatted as `user:email`) or `VPC_SC_ALLOWED_MEMBERS` (comma-separated list of `user:email` or `serviceAccount:...`)

Or run manually:

```bash
cd agentic-lens/security/vpc_sc
terraform init
terraform plan -var="project_id=YOUR_PROJECT" -var="org_id=YOUR_ORG" -var='allowed_members=["user:you@example.com"]'
terraform apply -var=... -auto-approve
```
