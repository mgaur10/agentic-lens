import os
import sys
import traceback
import urllib.request
import vertexai
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from vertexai import types

PROJECT_ID = "agentic-ai-lens"
LOCATION = "us-central1"

# Target Gateways
EGRESS_GATEWAY = f"projects/{PROJECT_ID}/locations/{LOCATION}/agentGateways/main-egress-agw-v2"
INGRESS_GATEWAY = f"projects/{PROJECT_ID}/locations/{LOCATION}/agentGateways/main-ingress-agw"

print("Initializing Vertex AI SDK...")
vertexai.init(project=PROJECT_ID, location=LOCATION)

def fetch_url(url: str) -> str:
    """Fetches the content of a given URL and returns it as a string or reports the exception."""
    import urllib.request
    import ssl
    import os
    
    print(f"Attempting to fetch URL: {url}")
    try:
        # Respect unverified context to avoid bootstrap certificate conflicts if needed
        context = ssl._create_unverified_context()
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, context=context, timeout=10.0) as response:
            code = response.getcode()
            body = response.read().decode('utf-8', errors='ignore')
            return f"SUCCESS: Fetch completed with HTTP code {code}. Body length: {len(body)}"
    except Exception as e:
        import traceback
        return f"FAILED: Exception occurred during fetch: {str(e)}\nTraceback:\n{traceback.format_exc()}"

# Construct a simple agent with the tool
egress_agent = LlmAgent(
    name="egress_test_agent",
    instruction="You are an agent designed to test network reachability. Call fetch_url with the requested URL and report the result.",
    model="gemini-2.5-flash",
    tools=[FunctionTool(fetch_url)]
)

try:
    print("Deploying egress_test_agent via Vertex AI...")
    client = vertexai.Client(
        project=PROJECT_ID,
        location=LOCATION,
        http_options=dict(api_version="v1beta1")
    )
    
    remote_agent = client.agent_engines.create(
        agent=egress_agent,
        config={
            "display_name": "egress_test_agent",
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
                "no_proxy": "240.0.0.2,169.254.169.254,metadata,metadata.google.internal,.metadata.google.internal,.google.internal",
                "NO_PROXY": "240.0.0.2,169.254.169.254,metadata,metadata.google.internal,.metadata.google.internal,.google.internal",
                "GRPC_DNS_RESOLVER": "native"
            },
            "requirements": [
                "google-cloud-aiplatform[adk,agent_engines]>=1.140.0",
                "google-adk>=1.30.0",
                "opentelemetry-api",
                "opentelemetry-sdk",
                "opentelemetry-exporter-gcp-trace",
                "opentelemetry-exporter-otlp-proto-http",
                "opentelemetry-instrumentation-vertexai",
                "pydantic>=2.9.0",
                "cloudpickle"
            ],
            "staging_bucket": "gs://agentic-ai-lens-staging"
        }
    )
    print(f"Deployment SUCCESS! Agent Engine URI: {remote_agent.api_resource.name}")
    print("Saving Agent Engine ID to egress_test_agent_id.txt in script directory")
    id_file_path = os.path.join(os.path.dirname(__file__), "egress_test_agent_id.txt")
    with open(id_file_path, "w") as f:
        f.write(remote_agent.api_resource.name)
except Exception as e:
    print("--- DEPLOYMENT EXCEPTION ---")
    traceback.print_exc()
    print("----------------------------")
