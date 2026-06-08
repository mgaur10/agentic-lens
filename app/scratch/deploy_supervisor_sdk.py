import os
import sys
import traceback
import vertexai
from vertexai import types
from google.cloud import aiplatform_v1beta1

PROJECT_ID = "agentic-security-dev"
LOCATION = "us-central1"

# Ingress and Egress Gateways
EGRESS_GATEWAY = f"projects/{PROJECT_ID}/locations/{LOCATION}/agentGateways/main-egress-agw-v2"
INGRESS_GATEWAY = f"projects/{PROJECT_ID}/locations/{LOCATION}/agentGateways/main-ingress-agw"

print(f"Initializing Vertex AI SDK... project={PROJECT_ID}, location={LOCATION}")
vertexai.init(project=PROJECT_ID, location=LOCATION)

# Change working directory to supervisor's parent so ADK imports resolve correctly
os.chdir("/usr/local/google/home/manishkgaur/Desktop/Workspace/Agent-gateway/agentic-lens/app/agentic-lens/agents")
sys.path.insert(0, "/usr/local/google/home/manishkgaur/Desktop/Workspace/Agent-gateway/agentic-lens/app/agentic-lens/agents")

try:
    print("Importing supervisor agent...")
    from supervisor.agent import root_agent
    
    print("Deploying supervisor agent via vertexai SDK...")
    client = vertexai.Client(
        project=PROJECT_ID,
        location=LOCATION,
        http_options=dict(api_version="v1beta1")
    )
    
    # Match deploy.sh specifications
    remote_agent = client.agent_engines.create(
        agent=root_agent,
        config={
            "display_name": "supervisor",
            "agent_gateway_config": {
                "agent_to_anywhere_config": {"agent_gateway": EGRESS_GATEWAY},
                "client_to_agent_config": {"agent_gateway": INGRESS_GATEWAY},
            },
            "identity_type": types.IdentityType.AGENT_IDENTITY,
            "env_vars": {
                "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
                "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental",
                "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "EVENT_ONLY",
                "GOOGLE_GENAI_USE_VERTEXAI": "true",
                "PYTHONHTTPSVERIFY": "0",
                "no_proxy": "googleapis.com,.googleapis.com,metadata.google.internal,.metadata.google.internal,.google.internal,169.254.169.254,metadata,github.com,.github.com,.githubusercontent.com,240.0.0.2,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
                "NO_PROXY": "googleapis.com,.googleapis.com,metadata.google.internal,.metadata.google.internal,.google.internal,169.254.169.254,metadata,github.com,.github.com,.githubusercontent.com,240.0.0.2,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16",
                "GRPC_DNS_RESOLVER": "native"
            },
            "requirements": [
                "google-cloud-aiplatform[adk,agent_engines]>=1.70.0",
                "google-adk>=1.5.0",
                "opentelemetry-api",
                "opentelemetry-sdk",
                "opentelemetry-exporter-gcp-trace",
                "opentelemetry-exporter-otlp-proto-http",
                "opentelemetry-instrumentation-vertexai",
                "pydantic>=2.9.0",
                "cloudpickle>=2.0.0,<3",
                "deprecated>=1.2.0"
            ],
            "staging_bucket": "gs://agentic-security-dev-staging",
            "extra_packages": [
                "supervisor/supervisor_core",
                "supervisor/peer_agents"
            ]
        }
    )
    print(f"Deployment SUCCESS! Agent ID: {remote_agent.name}")
except Exception as e:
    print("--- DEPLOYMENT EXCEPTION ---")
    traceback.print_exc()
    print("----------------------------")
