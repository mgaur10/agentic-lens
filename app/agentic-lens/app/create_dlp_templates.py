#!/usr/bin/env python3
"""
Create Cloud DLP inspect and deidentify templates in the given region using standard urllib REST requests.
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

INFO_TYPES = [
    "US_SOCIAL_SECURITY_NUMBER",
    "EMAIL_ADDRESS",
    "GCP_API_KEY",
    "GCP_CREDENTIALS",
    "CREDIT_CARD_NUMBER",
    "BLOOD_TYPE",
    "FDA_CODE",
    "ICD10_CODE",
    "ICD9_CODE",
    "MEDICAL_TERM",
]

INSPECT_TEMPLATE_ID = "identification-template"
DEIDENTIFY_TEMPLATE_ID = "deidentify-replace-with-infotype"

def get_access_token():
    try:
        return subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    except Exception as e:
        print(f"ERROR: Failed to fetch access token via gcloud: {e}")
        sys.exit(1)

def make_post_request(url, payload, headers):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return None, (e.code, err_body)
    except Exception as e:
        return None, (500, str(e))

def main():
    print(f"Bootstrapping DLP templates in projects/{PROJECT_ID}/locations/{LOCATION}...")
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "x-goog-user-project": PROJECT_ID
    }
    
    # --- 1. Inspect Template ---
    inspect_url = f"https://dlp.googleapis.com/v2/projects/{PROJECT_ID}/locations/{LOCATION}/inspectTemplates"
    inspect_payload = {
        "inspectTemplate": {
            "displayName": "Identification template",
            "description": "Detects SSN, email, GCP credentials, credit card, medical and FDA/ICD codes.",
            "inspectConfig": {
                "infoTypes": [{"name": name} for name in INFO_TYPES],
                "minLikelihood": "POSSIBLE",
                "includeQuote": True
            }
        },
        "templateId": INSPECT_TEMPLATE_ID
    }
    
    print("Creating DLP inspect template (identification)...")
    res, err = make_post_request(inspect_url, inspect_payload, headers)
    if err:
        code, body = err
        if "already exists" in body.lower() or "already_exists" in body.lower() or "already in use" in body.lower() or code == 409:
            print(f"  Template {INSPECT_TEMPLATE_ID} already exists/in-use; skipping.")
        else:
            print(f"  ERROR creating inspect template: {body}")
            sys.exit(1)
    else:
        print(f"  Created: {res.get('name')}")

    # --- 2. Deidentify Template ---
    deidentify_url = f"https://dlp.googleapis.com/v2/projects/{PROJECT_ID}/locations/{LOCATION}/deidentifyTemplates"
    deidentify_payload = {
        "deidentifyTemplate": {
            "displayName": "Deidentify replace with info type",
            "description": "Replaces sensitive text with the info type name (e.g. [EMAIL_ADDRESS]).",
            "deidentifyConfig": {
                "infoTypeTransformations": {
                    "transformations": [
                        {
                            "infoTypes": [{"name": name} for name in INFO_TYPES],
                            "primitiveTransformation": {
                                "replaceWithInfoTypeConfig": {}
                            }
                        }
                    ]
                }
            }
        },
        "templateId": DEIDENTIFY_TEMPLATE_ID
    }

    print("Creating DLP deidentify template (replace with info type)...")
    res, err = make_post_request(deidentify_url, deidentify_payload, headers)
    if err:
        code, body = err
        if "already exists" in body.lower() or "already_exists" in body.lower() or "already in use" in body.lower() or code == 409:
            print(f"  Template {DEIDENTIFY_TEMPLATE_ID} already exists/in-use; skipping.")
        else:
            print(f"  ERROR creating deidentify template: {body}")
            sys.exit(1)
    else:
        print(f"  Created: {res.get('name')}")

    print("")
    print("Done. Templates:")
    print(f"  Inspect:    projects/{PROJECT_ID}/locations/{LOCATION}/inspectTemplates/{INSPECT_TEMPLATE_ID}")
    print(f"  Deidentify: projects/{PROJECT_ID}/locations/{LOCATION}/deidentifyTemplates/{DEIDENTIFY_TEMPLATE_ID}")

if __name__ == "__main__":
    main()
