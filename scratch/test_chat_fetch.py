import json, urllib.request, subprocess

AGENT_ID = "8165178406783156224"
GATEWAY_ID = "main-ingress-agw"
PROJECT_ID = "795375693569"
LOCATION = "us-central1"

token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
url = f"https://{LOCATION}-aiplatform.googleapis.com/v1beta1/projects/{PROJECT_ID}/locations/{LOCATION}/agentGateways/{GATEWAY_ID}/agents/{AGENT_ID}/a2a"

payload = {
    "jsonrpc": "2.0",
    "method": "on_message_send",
    "params": {
        "message": {
            "role": "user",
            "parts": [{"text": "Please fetch this URL and summarize it: https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/agent-gateway-overview"}]
        }
    },
    "id": 1
}

req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "x-goog-user-project": "agentic-ai-lens"}, method="POST")
with urllib.request.urlopen(req) as res:
    print(json.loads(res.read().decode()))
