#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"

SERVICE_NAME_DEFAULT="ai-prism-agent-glass-ui"
SERVICE_NAME="${SERVICE_NAME:-$SERVICE_NAME_DEFAULT}"

if [[ -z "${GCP_PROJECT_ID:-}" ]]; then
  echo "ERROR: GCP_PROJECT_ID env var must be set."
  exit 1
fi

# Match Vertex / versions.env default (us-central1) unless REGION is set.
REGION="${REGION:-us-central1}"

# Cloud Run request timeout (seconds). One /api/query call runs Supervisor then a department engine
# sequentially; each hop can take several minutes (Engineering: Scout→Coder→Quality and Security Reviewer). Default 300s
# is too low and causes opaque browser failures. Override with GLASS_UI_CLOUD_RUN_TIMEOUT_S (max 3600).
# Default 1800s: supervisor (300) + department (1200) + margin; X-Ray-only fast path still needs headroom.
GLASS_UI_CLOUD_RUN_TIMEOUT_S="${GLASS_UI_CLOUD_RUN_TIMEOUT_S:-1800}"

# Access: default is private Cloud Run + IAP SA invoker (production). For direct Cloud Run testing
# while IAP / HTTPS LB is off, set GLASS_UI_ALLOW_UNAUTHENTICATED=1 so the service allows
# unauthenticated invoke (allUsers:run.invoker). Revert to default before production.
# If your org blocks allUsers, use GLASS_UI_EXTRA_INVOKERS instead (comma-separated), e.g.
#   GLASS_UI_EXTRA_INVOKERS="user:alice@example.com,user:bob@example.com"
GLASS_UI_ALLOW_UNAUTHENTICATED="${GLASS_UI_ALLOW_UNAUTHENTICATED:-0}"
GLASS_UI_EXTRA_INVOKERS="${GLASS_UI_EXTRA_INVOKERS:-}"

# Required env vars for Cloud Run
# google-genai: allow ADC token refresh when calling Vertex Agent Engine APIs (reduces 401s).
ENV_VARS="GCP_PROJECT_ID=${GCP_PROJECT_ID},GCP_LOCATION=${REGION},GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES=false,GRPC_DNS_RESOLVER=native"

# Optional: pass through Supervisor/engine IDs for routing
if [[ -n "${AGENTIC_LENS_SUPERVISOR_ENGINE:-}" ]]; then
  ENV_VARS="${ENV_VARS},AGENTIC_LENS_SUPERVISOR_ENGINE=${AGENTIC_LENS_SUPERVISOR_ENGINE}"
fi
if [[ -n "${SUPERVISOR_ENGINE_ID:-}" ]]; then
  ENV_VARS="${ENV_VARS},SUPERVISOR_ENGINE_ID=${SUPERVISOR_ENGINE_ID}"
fi
# Department engines (required for two-hop routing after Supervisor JSON / transfer resolution)
for _k in CHAT_ENGINE_ID ENG_ENGINE_ID EVENTS_ENGINE_ID XRAY_ENGINE_ID; do
  _v="${!_k:-}"
  if [[ -n "${_v}" ]]; then
    ENV_VARS="${ENV_VARS},${_k}=${_v}"
  fi
done
unset _k _v
# Stream timeouts (passed to the container; Python defaults are 300s each if unset).
# Supervisor + department run one after another, so Cloud Run timeout must exceed their sum.
AGENT_ENGINE_SUPERVISOR_TIMEOUT_S="${AGENT_ENGINE_SUPERVISOR_TIMEOUT_S:-300}"
# X-Ray Terraform/repo IAM reports often need >600s (clone, tools, multi-step LLM).
AGENT_ENGINE_DEPARTMENT_TIMEOUT_S="${AGENT_ENGINE_DEPARTMENT_TIMEOUT_S:-1200}"
ENV_VARS="${ENV_VARS},AGENT_ENGINE_SUPERVISOR_TIMEOUT_S=${AGENT_ENGINE_SUPERVISOR_TIMEOUT_S}"
ENV_VARS="${ENV_VARS},AGENT_ENGINE_DEPARTMENT_TIMEOUT_S=${AGENT_ENGINE_DEPARTMENT_TIMEOUT_S}"
for _k in AGENT_ENGINE_DEBUG_SUPERVISOR_STREAM AGENT_ENGINE_DEBUG_STREAM; do
  _v="${!_k:-}"
  if [[ -n "${_v}" ]]; then
    ENV_VARS="${ENV_VARS},${_k}=${_v}"
  fi
done
unset _k _v
if [[ -n "${GLASS_UI_LOGS_FIRESTORE_DATABASE:-}" ]]; then
  ENV_VARS="${ENV_VARS},GLASS_UI_LOGS_FIRESTORE_DATABASE=${GLASS_UI_LOGS_FIRESTORE_DATABASE}"
fi
ENV_VARS="${ENV_VARS},LENS_STRICT_ENGINE_STREAM=true"

IMAGE="us-central1-docker.pkg.dev/${GCP_PROJECT_ID}/prism-glass-ui/ai-prism-agent-glass-ui"

echo "Building image ${IMAGE} with cloudbuild_glass_ui.yaml..."
gcloud builds submit \
  --project "${GCP_PROJECT_ID}" \
  --config "${ROOT_DIR}/cloudbuild_glass_ui.yaml" \
  "${ROOT_DIR}"

if [[ "${GLASS_UI_ALLOW_UNAUTHENTICATED}" == "1" || "${GLASS_UI_ALLOW_UNAUTHENTICATED}" == "true" ]]; then
  echo "Deploying Cloud Run service ${SERVICE_NAME} (GLASS_UI_ALLOW_UNAUTHENTICATED=1 → public invoke)..."
  AUTH_FLAG=(--allow-unauthenticated --ingress=all --no-iap)
else
  echo "Deploying Cloud Run service ${SERVICE_NAME} (private invoke; use IAP or authenticated users)..."
  AUTH_FLAG=(--no-allow-unauthenticated --ingress=all --iap)
fi

gcloud run deploy "${SERVICE_NAME}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --project "${GCP_PROJECT_ID}" \
  "${AUTH_FLAG[@]}" \
  --memory 8Gi \
  --cpu 4 \
  --min-instances 1 \
  --max-instances 5 \
  --timeout "${GLASS_UI_CLOUD_RUN_TIMEOUT_S}" \
  --network=gemini-corp-vpc \
  --subnet=gemini-corp-swp-subnet \
  --vpc-egress=private-ranges-only \
  --set-env-vars "${ENV_VARS}"

PROJECT_NUMBER="$(gcloud projects describe "${GCP_PROJECT_ID}" --format='value(projectNumber)')"
IAP_SA="service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com"

if [[ -n "${GLASS_UI_EXTRA_INVOKERS// /}" ]]; then
  echo "Adding extra Cloud Run invokers (GLASS_UI_EXTRA_INVOKERS)..."
  _IFS=$IFS
  IFS=','
  # shellcheck disable=SC2086
  set -- ${GLASS_UI_EXTRA_INVOKERS}
  IFS=$_IFS
  for _member in "$@"; do
    _m=$(echo "${_member}" | xargs)
    [[ -z "${_m}" ]] && continue
    echo "  → ${_m}"
    gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
      --region="${REGION}" \
      --project="${GCP_PROJECT_ID}" \
      --member="${_m}" \
      --role="roles/run.invoker" \
      --quiet || echo "WARNING: failed to add invoker ${_m}"
  done
  unset _member _m _IFS
fi

if [[ "${GLASS_UI_ALLOW_UNAUTHENTICATED}" == "1" || "${GLASS_UI_ALLOW_UNAUTHENTICATED}" == "true" ]]; then
  echo "Skipping IAP service-account invoker (public Cloud Run; re-run deploy without GLASS_UI_ALLOW_UNAUTHENTICATED when IAP is back)."
else
  echo "Removing public invoker binding (allUsers) if present..."
  gcloud run services remove-iam-policy-binding "${SERVICE_NAME}" \
    --region="${REGION}" \
    --project="${GCP_PROJECT_ID}" \
    --member="allUsers" \
    --role="roles/run.invoker" \
    --quiet 2>/dev/null || true
fi

echo ""
echo "✅ Deployed Glass Prism UI service: ${SERVICE_NAME}"
if [[ "${GLASS_UI_ALLOW_UNAUTHENTICATED}" == "1" || "${GLASS_UI_ALLOW_UNAUTHENTICATED}" == "true" ]]; then
  echo "⚠️  Public invoke enabled. Unset GLASS_UI_ALLOW_UNAUTHENTICATED and redeploy before locking down with IAP again."
fi
echo "Cloud Run request timeout: ${GLASS_UI_CLOUD_RUN_TIMEOUT_S}s (GLASS_UI_CLOUD_RUN_TIMEOUT_S); engine timeouts: supervisor=${AGENT_ENGINE_SUPERVISOR_TIMEOUT_S}s, department=${AGENT_ENGINE_DEPARTMENT_TIMEOUT_S}s."
echo "If users see HTTP 504 'upstream request timeout' in the browser, check IAP / HTTPS LB backend timeout (often 30–60s default) and raise it to at least match Cloud Run."
echo "Tip: export CHAT_ENGINE_ID, ENG_ENGINE_ID, EVENTS_ENGINE_ID, XRAY_ENGINE_ID (and optional timeout vars) for full routing."
echo "Optional: set AGENTIC_LENS_SUPERVISOR_ENGINE (or SUPERVISOR_ENGINE_ID) before deploy for Supervisor routing."

