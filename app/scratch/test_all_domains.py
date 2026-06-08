#!/usr/bin/env python3
import json
import urllib.request
import urllib.error
import subprocess
import urllib.parse
import sys

PROJECT_ID = "795375693569" # Numeric project ID
PROJECT_NAME = "agentic-ai-lens" # String project name
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
            return response.status, response.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = str(e)
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

    domains = [
        "us-central1-aiplatform.googleapis.com",
        "aiplatform.googleapis.com",
        "us-central1-networkservices.googleapis.com",
        "networkservices.googleapis.com",
        "us-central1-agentregistry.googleapis.com",
        "agentregistry.googleapis.com",
    ]

    versions = ["v1alpha", "v1beta1", "v1"]

    candidates = {
        "displayName": "chat",
        "reasoningEngineId": "8165178406783156224",
        "registryUid": AGENT_UID,
    }

    suffixes = [
        "/a2a",
        "/mcp",
        ":query",
        ":streamQuery",
        ":predict",
        "/query",
        "",
    ]

    payload = {
        "jsonrpc": "2.0",
        "method": "on_message_send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"text": "Hello"}]
            }
        },
        "id": 1
    }

    print("Starting domain/endpoint matrix scanning...")
    count = 0
    for domain in domains:
        for version in versions:
            for p_id in [PROJECT_ID, PROJECT_NAME]:
                for agent_label, agent_val in candidates.items():
                    for suffix in suffixes:
                        count += 1
                        url = f"https://{domain}/{version}/projects/{p_id}/locations/{LOCATION}/agentGateways/{GATEWAY_ID}/agents/{agent_val}{suffix}"
                        status, res, err = make_post_request(url, payload, headers)
                        if status != 404:
                            print(f"[FOUND NON-404] Domain: {domain} | Version: {version} | Project: {p_id} | Agent: {agent_label} | Suffix: {suffix} -> Status: {status}")
                            if res:
                                print(f"  Response: {res[:300]}")
                            else:
                                print(f"  Error: {err[:300]}")
                        
                        # Also test unencoded URN format if it could be a project level path
                        if agent_label == "registryUid":
                            full_agent_name = f"projects/{PROJECT_NAME}/locations/{LOCATION}/agents/{agent_val}"
                            encoded_agent_name = urllib.parse.quote(full_agent_name, safe="")
                            url_full = f"https://{domain}/{version}/projects/{p_id}/locations/{LOCATION}/agentGateways/{GATEWAY_ID}/agents/{encoded_agent_name}{suffix}"
                            status_f, res_f, err_f = make_post_request(url_full, payload, headers)
                            if status_f != 404:
                                print(f"[FOUND NON-404 FULL-NAME] Domain: {domain} | Version: {version} | Project: {p_id} | Suffix: {suffix} -> Status: {status_f}")
                                if res_f:
                                    print(f"  Response: {res_f[:300]}")
                                else:
                                    print(f"  Error: {err_f[:300]}")

    print(f"Completed scanning {count} URL variations.")

if __name__ == "__main__":
    main()
