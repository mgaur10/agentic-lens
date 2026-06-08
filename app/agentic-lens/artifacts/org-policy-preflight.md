# Organization policy pre-flight

Complete **before Phase 1** when the new project sits under enterprise guardrails.

## Policy vs deployment

| Org constraint | Agentic Prism need | If violated |
|----------------|-------------------|-------------|
| `constraints/gcp.resourceLocations` | `REGION` in allowlist | Change `versions.env` REGION |
| `constraints/iam.disableServiceAccountKeyCreation` | OK — uses Agent Identity | No JSON keys |
| `constraints/run.allowedIngress` | IAP or internal only | Do not use public Run in prod |
| `constraints/iam.allowedPolicyMemberDomains` | IAP users in allowed domains | Fix IAP group members |
| CMEK required | `AGENT_ENGINE_KMS_KEY_*` in versions.env | Run step 05 or org keys |
| VPC-SC | Storage + AR ingress for RE SA | See `vpc-sc-ingress.md` |
| `constraints/compute.restrictVpcPeering` | May affect LB | Use serverless NEG pattern |

## Console steps

1. **IAM & Admin → Organization policies** — filter policies on project.
2. Export policy names that **deny** or **enforce** for: Run, Vertex, KMS, Secret Manager, `allUsers`.
3. Record exceptions or tag-based rules.

## Worksheet

| Policy constraint | Enforced? | Action for deploy |
|-------------------|-----------|-------------------|
| Resource locations | | |
| SA key creation disabled | | |
| Public Cloud Run denied | | Use IAP |
| CMEK required | | |
| VPC-SC | | Skip repo step 12 if org owns perimeter |

## Repo skip flags

If org already enforced equivalent controls:

```bash
# migration/config/migration.env
SKIP_INFRA_MODEL_ARMOR=1
SKIP_INFRA_CMEK=1
SKIP_INFRA_VPC_SC=1
```

Document org resource IDs in `resource-inventory.csv`.
