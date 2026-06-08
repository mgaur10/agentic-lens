#!/usr/bin/env python3
import json
import subprocess
import sys

PROJECT_ID = "agentic-ai-lens"
LOCATION = "us-central1"
BASE_URL = f"https://agentregistry.googleapis.com/v1alpha/projects/{PROJECT_ID}/locations/{LOCATION}"

services = [
    {
        "id": "logging",
        "displayName": "Cloud Logging",
        "description": "Google Cloud Logging API",
        "url": "https://logging.googleapis.com"
    },
    {
        "id": "cloudresourcemanager",
        "displayName": "Cloud Resource Manager",
        "description": "Google Cloud Resource Manager API",
        "url": "https://cloudresourcemanager.googleapis.com"
    },
    {
        "id": "cloudresourcemanager-mtls",
        "displayName": "Cloud Resource Manager mTLS",
        "description": "Google Cloud Resource Manager mTLS API",
        "url": "https://cloudresourcemanager.mtls.googleapis.com"
    },
    {
        "id": "storage",
        "displayName": "Cloud Storage",
        "description": "Google Cloud Storage API",
        "url": "https://storage.googleapis.com"
    },
    {
        "id": "cloudtrace",
        "displayName": "Cloud Trace",
        "description": "Google Cloud Trace API",
        "url": "https://cloudtrace.googleapis.com"
    },
    {
        "id": "github",
        "displayName": "GitHub",
        "description": "GitHub Website",
        "url": "https://github.com"
    },
    {
        "id": "api-github",
        "displayName": "GitHub API",
        "description": "GitHub REST API",
        "url": "https://api.github.com"
    },
    {
        "id": "raw-github",
        "displayName": "GitHub Raw Content",
        "description": "GitHub Raw Content API",
        "url": "https://raw.githubusercontent.com"
    },
    {
        "id": "googleapis",
        "displayName": "Google APIs",
        "description": "Google APIs Default Endpoint",
        "url": "https://www.googleapis.com"
    },
    {
        "id": "googleapis-psc",
        "displayName": "Google APIs PSC VIP",
        "description": "Google APIs PSC Private VIP",
        "url": "https://240.0.0.2"
    },
    {
        "id": "googleapis-psc-port",
        "displayName": "Google APIs PSC VIP with Port",
        "description": "Google APIs PSC Private VIP with Port 443",
        "url": "https://240.0.0.2:443"
    },
    {
        "id": "gcp-docs",
        "displayName": "Google Cloud Docs",
        "description": "Google Cloud Documentation",
        "url": "https://docs.cloud.google.com"
    },
    {
        "id": "google-web",
        "displayName": "Google Web",
        "description": "Google Web Search",
        "url": "https://www.google.com"
    },
    {
        "id": "iamcredentials",
        "displayName": "IAM Credentials API",
        "description": "Google IAM Credentials API",
        "url": "https://iamcredentials.googleapis.com"
    },
    {
        "id": "oauth2",
        "displayName": "OAuth2 API",
        "description": "Google OAuth2 API",
        "url": "https://oauth2.googleapis.com"
    },
    {
        "id": "aiplatform",
        "displayName": "Vertex AI Platform",
        "description": "Google Vertex AI Platform Global API",
        "url": "https://aiplatform.googleapis.com"
    },
    {
        "id": "us-central1-aiplatform-mtls",
        "displayName": "Vertex AI Platform mTLS us-central1",
        "description": "Vertex AI Platform us-central1 mTLS API",
        "url": "https://us-central1-aiplatform.mtls.googleapis.com"
    },
    {
        "id": "us-central1-aiplatform",
        "displayName": "Vertex AI Platform us-central1",
        "description": "Vertex AI Platform us-central1 regional API",
        "url": "https://us-central1-aiplatform.googleapis.com"
    },
    {
        "id": "terraform",
        "displayName": "Terraform",
        "description": "HashiCorp Terraform Registry",
        "url": "https://terraform.io"
    }
]

def get_access_token():
    res = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, check=True)
    return res.stdout.strip()

def check_service_exists(service_id, token):
    url = f"{BASE_URL}/services/{service_id}"
    res = subprocess.run([
        "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
        "-H", f"Authorization: Bearer {token}",
        url
    ], capture_output=True, text=True)
    return res.stdout.strip() == "200"

def register_service(service, token):
    url = f"{BASE_URL}/services?serviceId={service['id']}"
    payload = {
        "displayName": service["displayName"],
        "description": service["description"],
        "interfaces": [
            {
                "url": service["url"],
                "protocolBinding": "JSONRPC"
            }
        ],
        "endpointSpec": {
            "type": "NO_SPEC"
        }
    }
    res = subprocess.run([
        "curl", "-s", "-X", "POST",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
        url
    ], capture_output=True, text=True)
    
    try:
        data = json.loads(res.stdout)
        if "name" in data and "operations" in data["name"]:
            print(f"  Created operation: {data['name']}")
            return True
        else:
            print(f"  Error registering {service['id']}: {res.stdout}")
            return False
    except Exception as e:
        print(f"  Failed to parse response for {service['id']}: {res.stdout}, err: {e}")
        return False

def main():
    print("Obtaining access token...")
    try:
        token = get_access_token()
    except Exception as e:
        print(f"Failed to get access token: {e}")
        sys.exit(1)
        
    print(f"Found {len(services)} services to verify/register.")
    for s in services:
        print(f"Verifying service: {s['id']} ({s['displayName']})")
        if check_service_exists(s['id'], token):
            print(f"  Service {s['id']} already exists. Skipping.")
        else:
            print(f"  Service {s['id']} does not exist. Registering...")
            register_service(s, token)
            
    print("All services verified.")

if __name__ == "__main__":
    main()
