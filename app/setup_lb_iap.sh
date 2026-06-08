#!/usr/bin/env bash
set -euo pipefail

# Config
PROJECT_ID="agentic-ai-lens"
REGION="us-central1"
DOMAIN="agent-security.manishkgaur.demo.altostrat.com"
SERVICE_NAME="ai-prism-agent-glass-ui"

# Infrastructure Names
IP_NAME="glass-ui-global-ip"
NEG_NAME="glass-ui-serverless-neg"
BACKEND_NAME="glass-ui-backend"
URL_MAP_NAME="glass-ui-url-map"
CERT_NAME="glass-ui-cert"
PROXY_NAME="glass-ui-https-proxy"
FWD_RULE_NAME="glass-ui-fwd-rule"

echo "Provisioning Global External Application Load Balancer for $SERVICE_NAME..."

# 1. Reserve Global IP
echo "--- Reserving Global IP ---"
gcloud compute addresses create $IP_NAME --global --project=$PROJECT_ID || echo "IP may already exist."
IP_ADDRESS=$(gcloud compute addresses describe $IP_NAME --global --project=$PROJECT_ID --format="value(address)")
echo "✅ Reserved Global IP: $IP_ADDRESS"

# 2. Serverless NEG
echo "--- Creating Serverless NEG ---"
gcloud compute network-endpoint-groups create $NEG_NAME \
  --region=$REGION \
  --network-endpoint-type=serverless \
  --cloud-run-service=$SERVICE_NAME \
  --project=$PROJECT_ID || echo "NEG may already exist."

# 3. Backend Service
echo "--- Creating Backend Service ---"
gcloud compute backend-services create $BACKEND_NAME \
  --global \
  --project=$PROJECT_ID \
  --load-balancing-scheme=EXTERNAL_MANAGED || echo "Backend service may already exist."

gcloud compute backend-services add-backend $BACKEND_NAME \
  --global \
  --project=$PROJECT_ID \
  --network-endpoint-group=$NEG_NAME \
  --network-endpoint-group-region=$REGION || echo "Backend may already be added."


echo "--- Configuring IAP ---"
if [[ -n "${OAUTH_CLIENT_ID:-}" && -n "${OAUTH_CLIENT_SECRET:-}" ]]; then
  gcloud compute backend-services update $BACKEND_NAME \
    --global \
    --project=$PROJECT_ID \
    --iap=enabled,oauth2-client-id=${OAUTH_CLIENT_ID},oauth2-client-secret=${OAUTH_CLIENT_SECRET}
  echo "✅ IAP Enabled on Backend Service."
else
  echo "⚠️  OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET not provided. You will need to enable IAP on $BACKEND_NAME in the Cloud Console or rerun this script with them exported."
fi

# 4. URL Map
echo "--- Creating URL Map ---"
gcloud compute url-maps create $URL_MAP_NAME \
  --default-service=$BACKEND_NAME \
  --global \
  --project=$PROJECT_ID || echo "URL Map may already exist."

# 5. SSL Certificate
echo "--- Creating Google-Managed SSL Certificate ---"
gcloud compute ssl-certificates create $CERT_NAME \
  --domains=$DOMAIN \
  --global \
  --project=$PROJECT_ID || echo "SSL Certificate may already exist."

# 6. Target HTTPS Proxy
echo "--- Creating Target HTTPS Proxy ---"
gcloud compute target-https-proxies create $PROXY_NAME \
  --url-map=$URL_MAP_NAME \
  --ssl-certificates=$CERT_NAME \
  --global \
  --project=$PROJECT_ID || echo "Target HTTPS Proxy may already exist."

# 7. Forwarding Rule
echo "--- Creating Forwarding Rule ---"
gcloud compute forwarding-rules create $FWD_RULE_NAME \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --network-tier=PREMIUM \
  --address=$IP_NAME \
  --global \
  --target-https-proxy=$PROXY_NAME \
  --ports=443 \
  --project=$PROJECT_ID || echo "Forwarding Rule may already exist."

echo ""
echo "============================================================"
echo "✅ Load Balancer Deployment Complete!"
echo "============================================================"
echo "ACTION REQUIRED: Update your DNS Settings for:"
echo "$DOMAIN"
echo ""
echo "Create an A Record pointing to this IP Address:"
echo "$IP_ADDRESS"
echo "============================================================"
echo ""
echo "Note: The Google-managed SSL Certificate will remain in 'PROVISIONING' state until DNS propagates."
echo "Model Armor Note: Since the extension was created in us-central1 and this is a Global LB, it's best to attach the 'gemini-corp-ma-extension' to the '$BACKEND_NAME' via the Cloud Console > Load Balancing > Extensions tab once it appears, to ensure the cross-region policies map correctly."
