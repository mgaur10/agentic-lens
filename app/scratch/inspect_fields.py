import os
from google.cloud import aiplatform_v1beta1 as aiplatform

os.environ["GCP_PROJECT_ID"] = "agentic-ai-lens"
os.environ["GOOGLE_CLOUD_PROJECT"] = "agentic-ai-lens"
os.environ["GCP_LOCATION"] = "us-central1"

def main():
    client = aiplatform.ReasoningEngineServiceClient(
        client_options={"api_endpoint": "us-central1-aiplatform.googleapis.com"}
    )
    res = client.get_reasoning_engine(name="projects/795375693569/locations/us-central1/reasoningEngines/8165178406783156224")
    
    print("res.context_spec fields:")
    context_spec = res.context_spec
    for key in dir(context_spec):
        if not key.startswith("_"):
            try:
                val = getattr(context_spec, key)
                print(f" - {key}: {type(val)}")
                if key == "client_to_agent_config" or "gateway" in key.lower() or "client" in key.lower():
                    print(f"   Value: {val}")
            except Exception as e:
                print(f" - {key}: ERROR {e}")

if __name__ == "__main__":
    main()
