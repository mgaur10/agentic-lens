import os
import json
import subprocess
import urllib.request
import urllib.error

PROJECT_ID = "795375693569"
LOCATION = "us-central1"
GATEWAY_ID = "main-ingress-agw"
AGENT_UID = "agentregistry-00000000-0000-0000-74d8-7d4eacbf990f" # Chat registry UID

def get_access_token():
    return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()

def make_post_request(url, payload, headers):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, response.read().decode("utf-8"), None
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
        "x-goog-user-project": "agentic-ai-lens"
    }
    
    suffixes = [
        "",
        "/a2a",
        "/mcp",
        ":query",
        ":streamQuery",
    ]
    
    payload_rpc = {
        "jsonrpc": "2.0",
        "method": "on_message_send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"text": "Hello, suffix test."}]
            }
        },
        "id": 1
    }
    
    payload_direct = {
        "message": "Hello, direct payload test."
    }
    
    # We will test both JSON-RPC payload and standard query payload
    for payload_type, payload in [("JSON-RPC", payload_rpc), ("Direct", payload_direct)]:
        print(f"\n================= TESTING PAYLOAD TYPE: {payload_type} =================")
        for version in ["v1alpha", "v1beta1"]:
            for suffix in suffixes:
                url = f"https://{LOCATION}-aiplatform.googleapis.com/{version}/projects/{PROJECT_ID}/locations/{LOCATION}/agentGateways/{GATEWAY_ID}/agents/{AGENT_UID}{suffix}"
                print(f"Testing {version} with suffix '{suffix}' -> {url}")
                status, res, err = make_post_request(url, payload, headers)
                if res:
                    print(f"  Result: SUCCESS (Status {status})\n  {res[:300]}...")
                else:
                    # Let's print the start of error body to check if it's 404 or something else
                    clean_err = err.replace("\n", " ").strip()
                    print(f"  Result: ERROR {status} - {clean_err[:300]}")

if __name__ == "__main__":
    main()
