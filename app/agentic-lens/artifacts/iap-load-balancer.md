# Phase 6 — IAP and HTTPS load balancer

Production pattern for **private** Cloud Run (`ai-prism-agent-glass-ui`).

## Architecture

```text
User → HTTPS LB (managed cert) → IAP → Serverless NEG → Cloud Run
```

## 1. Serverless NEG

```bash
source versions.env

gcloud compute network-endpoint-groups create glass-ui-neg \
  --region="${REGION}" \
  --network-endpoint-type=serverless \
  --cloud-run-service=ai-prism-agent-glass-ui \
  --project="${PROJECT_ID}"
```

## 2. Backend service

```bash
gcloud compute backend-services create glass-ui-backend \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --project="${PROJECT_ID}"

gcloud compute backend-services add-backend glass-ui-backend \
  --global \
  --network-endpoint-group=glass-ui-neg \
  --network-endpoint-group-region="${REGION}" \
  --project="${PROJECT_ID}"
```

**Timeout:** set backend timeout to **≥ 1800 seconds** (Engineering + X-Ray queries).

## 3. URL map, proxy, forwarding rule

Prefer Console: **Network Services → Load balancing → Create HTTP(S) load balancer**.

- Backend: `glass-ui-backend`
- Frontend: HTTPS, managed certificate for your hostname

## 4. IAP

1. **Security → Identity-Aware Proxy**
2. Enable IAP on the HTTPS backend resource
3. Grant `roles/iap.httpsResourceAccessor` to users/groups

## 5. Cloud Run invoker for IAP

```bash
PN=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')
IAP_SA="service-${PN}@gcp-sa-iap.iam.gserviceaccount.com"

gcloud run services add-iam-policy-binding ai-prism-agent-glass-ui \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${IAP_SA}" \
  --role="roles/run.invoker"
```

(`deploy-glass-ui.sh` does this when not using public invoke.)

## 6. Smoke with IAP

```bash
export GLASS_UI_URL="https://your-hostname.example.com"
export IAP_OAUTH_CLIENT_ID="....apps.googleusercontent.com"
python3 scripts/smoke_glass_ui_departments.py --profile smoke
```

## 7. Remove public access

Ensure `GLASS_UI_ALLOW_UNAUTHENTICATED` is **not** set; redeploy Glass UI if needed.
