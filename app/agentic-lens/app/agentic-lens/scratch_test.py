import os
import sys
import vertexai
from google.auth import default as google_auth_default

def check_engine(engine_id):
    print(f"Checking engine: {engine_id}")
    try:
        from vertexai import agent_engines
    except ImportError:
        from vertexai.preview import agent_engines

    project = "agentic-security-dev"
    location = "us-central1"
    
    credentials, _ = google_auth_default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    vertexai.init(project=project, location=location, credentials=credentials)
    
    try:
        engine = agent_engines.get(engine_id)
        print(f"SUCCESS: Engine found! Resource: {engine.resource_name}")
    except Exception as e:
        print(f"ERROR: Failed to get engine: {e}", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        check_engine(sys.argv[1])
    else:
        check_engine("projects/504643566830/locations/us-central1/reasoningEngines/319318517671264256")
