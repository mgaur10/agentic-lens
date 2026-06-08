import subprocess
import json
import urllib.request

PROJECT_ID = "agentic-security-dev"
LOCATION = "us-central1"

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

token = run_cmd("gcloud auth print-access-token")
url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
try:
    with urllib.request.urlopen(req) as response:
        res = json.loads(response.read().decode())
        print("Active Reasoning Engines:")
        for engine in res.get("reasoningEngines", []):
            print(f"- {engine.get('displayName')}: {engine.get('name')}")
except Exception as e:
    print("Error:", e)
