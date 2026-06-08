import os
import sys
from google.cloud import aiplatform_v1beta1 as aiplatform

os.environ["GCP_PROJECT_ID"] = "agentic-ai-lens"
os.environ["GOOGLE_CLOUD_PROJECT"] = "agentic-ai-lens"
os.environ["GCP_LOCATION"] = "us-central1"

def main():
    try:
        client = aiplatform.ReasoningEngineServiceClient(
            client_options={"api_endpoint": "us-central1-aiplatform.googleapis.com"}
        )
        res = client.get_reasoning_engine(name="projects/795375693569/locations/us-central1/reasoningEngines/8165178406783156224")
        print("Reasoning Engine Details:")
        print(f"Name: {res.name}")
        print(f"Display Name: {res.display_name}")
        print("Spec Config / Gateway Config:")
        if hasattr(res, "spec"):
            print(res.spec)
    except Exception as e:
        print(f"Error describing engine: {e}")

if __name__ == "__main__":
    main()
