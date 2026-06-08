#!/usr/bin/env python3
import json
import urllib.request
import urllib.error
import subprocess
import sys
import urllib.parse

PROJECT_ID = "795375693569" # Numeric project ID
LOCATION = "us-central1"
GATEWAY_ID = "main-ingress-agw"

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
        "x-goog-user-project": "agentic-ai-lens"
    }
    
    # Candidate agent IDs
    candidates = {
        "displayName": "chat",
        "reasoningEngineId": "8165178406783156224",
        "registryUid": "agentregistry-00000000-0000-0000-74d8-7d4eacbf990f",
        "full_path": "projects/795375693569/locations/us-central1/reasoningEngines/8165178406783156224"
    }
    
    # Candidate suffixes
    suffixes = [
        "",
        "/a2a",
        "/mcp",
        ":query",
        ":streamQuery",
        "/query",
        "/streamQuery",
        "/predict",
        ":predict",
    ]
    
    # Payloads
    payload_direct = {
        "input": {
            "message": "Hello from matrix test"
        }
    }
    
    print("Starting matrix testing...")
    
    for version in ["v1alpha", "v1beta1"]:
        print(f"\n================= TESTING {version} =================")
        for label, candidate in candidates.items():
            for suffix in suffixes:
                # Test standard encoded
                encoded_candidate = urllib.parse.quote(candidate, safe="")
                url = f"https://{LOCATION}-aiplatform.googleapis.com/{version}/projects/{PROJECT_ID}/locations/{LOCATION}/agentGateways/{GATEWAY_ID}/agents/{encoded_candidate}{suffix}"
                
                status, res, err = make_post_request(url, payload_direct, headers)
                if status != 404:
                    print(f"[FOUND NON-404] {label} ('{candidate}') with suffix '{suffix}' -> Status {status}")
                    if res:
                        print(f"  Response: {res[:200]}...")
                    else:
                        print(f"  Error payload: {err[:200]}...")
                
                # If full_path or contains slash, also test unencoded just in case
                if "/" in candidate:
                    url_unencoded = f"https://{LOCATION}-aiplatform.googleapis.com/{version}/projects/{PROJECT_ID}/locations/{LOCATION}/agentGateways/{GATEWAY_ID}/agents/{candidate}{suffix}"
                    status, res, err = make_post_request(url_unencoded, payload_direct, headers)
                    if status != 404:
                        print(f"[FOUND NON-404 UNENCODED] {label} with suffix '{suffix}' -> Status {status}")
                        if res:
                            print(f"  Response: {res[:200]}...")
                        else:
                            print(f"  Error payload: {err[:200]}...")

if __name__ == "__main__":
    main()
