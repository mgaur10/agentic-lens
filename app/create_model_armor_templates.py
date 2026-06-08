#!/usr/bin/env python3
"""
Create Model Armor security templates (security-medium, security-high) using standard urllib REST requests.
Matches the settings from setup_model_armor_templates.sh.
Requires zero external dependencies.
"""
import os
import sys
import json
import urllib.request
import subprocess

# Load .env if present
def _load_dotenv():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"\''))

_load_dotenv()

PROJECT_ID = (sys.argv[1] if len(sys.argv) > 1 else None) or os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "ai-prism-agent"
LOCATION = (sys.argv[2] if len(sys.argv) > 2 else None) or os.getenv("GCP_LOCATION") or "us-central1"
PROJECT_ID = PROJECT_ID.strip()
LOCATION = LOCATION.strip()

def get_access_token():
    try:
        return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    except Exception as e:
        print(f"ERROR: Failed to fetch access token via gcloud: {e}")
        sys.exit(1)

def make_request(url, payload, headers, method="POST"):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return None, (e.code, err_body)
    except Exception as e:
        return None, (500, str(e))

def main():
    print(f"Bootstrapping Model Armor templates in projects/{PROJECT_ID}/locations/{LOCATION}...")
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "x-goog-user-project": PROJECT_ID
    }
    
    if LOCATION == "global":
        base_url = f"https://modelarmor.googleapis.com/v1/projects/{PROJECT_ID}/locations/global/templates"
    else:
        base_url = f"https://modelarmor.{LOCATION}.rep.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/templates"

    # --- 1. Template: security-medium ---
    medium_url = f"{base_url}?templateId=security-medium"
    medium_payload = {
        "filterConfig": {
            "raiSettings": {
                "raiFilters": [
                    {"filterType": "HATE_SPEECH", "confidenceLevel": "MEDIUM_AND_ABOVE"},
                    {"filterType": "HARASSMENT", "confidenceLevel": "MEDIUM_AND_ABOVE"},
                    {"filterType": "SEXUALLY_EXPLICIT", "confidenceLevel": "MEDIUM_AND_ABOVE"},
                    {"filterType": "DANGEROUS", "confidenceLevel": "MEDIUM_AND_ABOVE"}
                ]
            },
            "sdpSettings": {
                "basicConfig": {
                    "filterEnforcement": "ENABLED"
                }
            },
            "piAndJailbreakFilterSettings": {
                "filterEnforcement": "ENABLED",
                "confidenceLevel": "MEDIUM_AND_ABOVE"
            },
            "maliciousUriFilterSettings": {
                "filterEnforcement": "ENABLED"
            }
        }
    }

    print("Creating template: security-medium...")
    res, err = make_request(medium_url, medium_payload, headers, method="POST")
    if err:
        code, body = err
        if "already exists" in body.lower() or "already_exists" in body.lower() or "already in use" in body.lower() or code == 409:
            print("  Template security-medium already exists/in-use; updating via PATCH...")
            patch_url = f"{base_url}/security-medium?updateMask=filterConfig"
            res, err = make_request(patch_url, medium_payload, headers, method="PATCH")
            if err:
                print(f"  ERROR updating security-medium template: {err[1]}")
                sys.exit(1)
            else:
                print(f"  Updated: {res.get('name')}")
        else:
            print(f"  ERROR creating security-medium template: {body}")
            sys.exit(1)
    else:
        print(f"  Created: {res.get('name')}")

    # --- 2. Template: security-high ---
    high_url = f"{base_url}?templateId=security-high"
    high_payload = {
        "filterConfig": {
            "raiSettings": {
                "raiFilters": [
                    {"filterType": "HATE_SPEECH", "confidenceLevel": "HIGH"},
                    {"filterType": "HARASSMENT", "confidenceLevel": "HIGH"},
                    {"filterType": "SEXUALLY_EXPLICIT", "confidenceLevel": "HIGH"},
                    {"filterType": "DANGEROUS", "confidenceLevel": "HIGH"}
                ]
            },
            "piAndJailbreakFilterSettings": {
                "filterEnforcement": "ENABLED",
                "confidenceLevel": "HIGH"
            },
            "maliciousUriFilterSettings": {
                "filterEnforcement": "ENABLED"
            },
            "sdpSettings": {
                "advancedConfig": {
                    "inspectTemplate": f"projects/{PROJECT_ID}/locations/{LOCATION}/inspectTemplates/identification-template",
                    "deidentifyTemplate": f"projects/{PROJECT_ID}/locations/{LOCATION}/deidentifyTemplates/deidentify-replace-with-infotype"
                }
            }
        }
    }

    print("Creating template: security-high...")
    res, err = make_request(high_url, high_payload, headers, method="POST")
    if err:
        code, body = err
        if "already exists" in body.lower() or "already_exists" in body.lower() or "already in use" in body.lower() or code == 409:
            print("  Template security-high already exists/in-use; updating via PATCH...")
            patch_url = f"{base_url}/security-high?updateMask=filterConfig"
            res, err = make_request(patch_url, high_payload, headers, method="PATCH")
            if err:
                print(f"  ERROR updating security-high template: {err[1]}")
                sys.exit(1)
            else:
                print(f"  Updated: {res.get('name')}")
        else:
            print(f"  ERROR creating security-high template: {body}")
            sys.exit(1)
    else:
        print(f"  Created: {res.get('name')}")

    print("")
    print("Done. Templates:")
    print(f"  - projects/{PROJECT_ID}/locations/{LOCATION}/templates/security-medium")
    print(f"  - projects/{PROJECT_ID}/locations/{LOCATION}/templates/security-high")

if __name__ == "__main__":
    main()
