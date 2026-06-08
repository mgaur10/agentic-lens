import os
import json
import subprocess
import urllib.request
import urllib.error

PROJECT_ID = "agentic-ai-lens"
LOCATION = "us-central1"

def get_access_token():
    return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()

def make_get_request(url, headers):
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return None, (e.code, err_body)
    except Exception as e:
        return None, (500, str(e))

def main():
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "x-goog-user-project": PROJECT_ID
    }
    
    url_agents = f"https://agentregistry.googleapis.com/v1alpha/projects/{PROJECT_ID}/locations/{LOCATION}/agents"
    res, err = make_get_request(url_agents, headers)
    if err:
        print(f"Error: {err[0]} - {err[1]}")
        return
        
    agents = res.get("agents", [])
    print(f"Found {len(agents)} agents in registry:")
    for a in agents:
        name = a.get("name")
        display_name = a.get("displayName")
        protocols = a.get("protocols", [])
        protocol_types = [p.get("type") for p in protocols]
        print(f" - Name: {name}")
        print(f"   DisplayName: {display_name}")
        print(f"   Protocols: {protocol_types}")
        for p in protocols:
            for interface in p.get("interfaces", []):
                print(f"     * ProtocolBinding: {interface.get('protocolBinding')}")
                print(f"       URL: {interface.get('url')}")

if __name__ == "__main__":
    main()
