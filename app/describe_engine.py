import subprocess
import json
import urllib.request

PROJECT_ID = "agentic-security-dev"
LOCATION = "us-central1"
ENGINE_ID = "6214042449728438272"  # newly deployed egress_test_agent engine ID

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

token = run_cmd("gcloud auth print-access-token")
url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{ENGINE_ID}"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
try:
    with urllib.request.urlopen(req) as response:
        res = json.loads(response.read().decode())
        print(json.dumps(res, indent=2))
except Exception as e:
    print("Error:", e)
