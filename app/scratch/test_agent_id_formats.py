import os
import json
import subprocess
import urllib.request
import urllib.error

PROJECT_ID = "795375693569" # Numeric project ID
PROJECT_NAME = "agentic-ai-lens" # String project name
LOCATION = "us-central1"
GATEWAY_ID = "main-ingress-agw"

def get_access_token():
    return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()

def make_post_request(url, payload, headers):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return e.code, None, err_body
    except Exception as e:
        return 500, None, str(e)

def main():
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "x-goog-user-project": PROJECT_NAME
    }
    
    # We will test the 'chat' agent
    # Different candidate values for {agent_id}:
    candidates = {
        "displayName": "chat",
        "reasoningEngineId": "8165178406783156224",
        "registryUid": "agentregistry-00000000-0000-0000-74d8-7d4eacbf990f",
        "urn": "urn:agent:projects-795375693569:projects:795375693569:locations:us-central1:aiplatform:reasoningEngines:8165178406783156224",
        # Maybe URN needs urlencoding? Let's check that too if URN fails
    }
    
    payload = {
        "jsonrpc": "2.0",
        "method": "on_message_send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"text": "Hello, this is a test of routing formats."}]
            }
        },
        "id": 1
    }
    
    # We will test projects/{PROJECT_ID} and projects/{PROJECT_NAME}
    for p_id in [PROJECT_ID, PROJECT_NAME]:
        print(f"\n================= TESTING PROJECT: {p_id} =================")
        for label, candidate in candidates.items():
            # URL encode the candidate if it has special characters (e.g. URN)
            import urllib.parse
            encoded_candidate = urllib.parse.quote(candidate, safe="")
            
            url = f"https://{LOCATION}-aiplatform.googleapis.com/v1alpha/projects/{p_id}/locations/{LOCATION}/agentGateways/{GATEWAY_ID}/agents/{encoded_candidate}/a2a"
            print(f"Testing {label} -> {url}")
            status, res, err = make_post_request(url, payload, headers)
            if res:
                print(f"  Result: SUCCESS (Status {status})\n  {json.dumps(res, indent=2)[:500]}...")
            else:
                print(f"  Result: ERROR {status} - {err[:300]}")

if __name__ == "__main__":
    main()
