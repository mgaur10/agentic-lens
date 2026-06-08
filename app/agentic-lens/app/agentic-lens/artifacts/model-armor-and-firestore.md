# Model Armor and Firestore (Phase 1)

## Model Armor

**Templates (repo Terraform step 04):**

| Template | Use |
|----------|-----|
| `security-medium` | Default UI toggle — RAI, jailbreak, malicious URI |
| `security-high` | Stricter + DLP de-identification |

**Verify:**

```bash
gcloud model-armor templates list --project=PROJECT_ID --location=REGION
```

If `SKIP_INFRA_MODEL_ARMOR=1`, document org template IDs in `resource-inventory.csv` and confirm Glass UI `backend/model_armor.py` template names match.

## Firestore

**Created by step 07** (typical database id: `xray-db`).

| Collection | Used by |
|------------|---------|
| `iam_knowledge_base` | xray_specialist, xray_auditor |
| `glass_ui_session_logs` | Glass UI (if `GLASS_UI_LOGS_FIRESTORE_DATABASE` set) |

**Env for agents:** `XRAY_KB_DATABASE=xray-db` (Agent Engine runtime if non-default).

**Verify:**

```bash
gcloud firestore databases list --project=PROJECT_ID
```
