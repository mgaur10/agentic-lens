#!/usr/bin/env python3
"""
Create Cloud DLP inspect and deidentify templates in the given region.

1. Inspect template (identification): detects the listed info types.
2. Deidentify template: replaces detected sensitive text with the info type name (e.g. [EMAIL_ADDRESS]).

Usage: python create_dlp_templates.py [PROJECT_ID] [LOCATION]
"""
import os
import sys

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

# Info types for identification and de-identification (same set for both templates)
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


def main():
    from google.cloud.dlp_v2.services.dlp_service import DlpServiceClient
    from google.cloud.dlp_v2.types import (
        DeidentifyConfig,
        DeidentifyTemplate,
        InspectConfig,
        InspectTemplate,
        InfoType,
        InfoTypeTransformations,
        Likelihood,
        PrimitiveTransformation,
        ReplaceWithInfoTypeConfig,
    )

    client = DlpServiceClient()
    parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"

    # --- 1. Inspect template (identification) ---
    # Do NOT set limits (max_findings_per_request): not supported when template is used for de-identification (Model Armor SDP).
    info_type_objects = [InfoType(name=name) for name in INFO_TYPES]
    inspect_config = InspectConfig(
        info_types=info_type_objects,
        min_likelihood=Likelihood.POSSIBLE,
        include_quote=True,
    )
    inspect_template = InspectTemplate(
        display_name="Identification template",
        description="Detects SSN, email, GCP credentials, credit card, medical and FDA/ICD codes.",
        inspect_config=inspect_config,
    )

    print("Creating DLP inspect template (identification)...")
    try:
        response = client.create_inspect_template(
            request={
                "parent": parent,
                "inspect_template": inspect_template,
                "template_id": INSPECT_TEMPLATE_ID,
            }
        )
        print(f"  Created: {response.name}")
    except Exception as e:
        err_msg = str(e).lower()
        if "already exists" in err_msg or "already in use" in err_msg:
            print(f"  Template {INSPECT_TEMPLATE_ID} already exists; skipping.")
        else:
            raise

    # --- 2. Deidentify template (replace with info type name) ---
    # One transformation: replace all listed info types with their type name
    transformation = InfoTypeTransformations.InfoTypeTransformation(
        info_types=info_type_objects,
        primitive_transformation=PrimitiveTransformation(
            replace_with_info_type_config=ReplaceWithInfoTypeConfig()
        ),
    )
    deidentify_config = DeidentifyConfig(
        info_type_transformations=InfoTypeTransformations(
            transformations=[transformation]
        )
    )
    deidentify_template = DeidentifyTemplate(
        display_name="Deidentify replace with info type",
        description="Replaces sensitive text with the info type name (e.g. [EMAIL_ADDRESS]).",
        deidentify_config=deidentify_config,
    )

    print("Creating DLP deidentify template (replace with info type)...")
    try:
        response = client.create_deidentify_template(
            request={
                "parent": parent,
                "deidentify_template": deidentify_template,
                "template_id": DEIDENTIFY_TEMPLATE_ID,
            }
        )
        print(f"  Created: {response.name}")
    except Exception as e:
        err_msg = str(e).lower()
        if "already exists" in err_msg or "already in use" in err_msg:
            print(f"  Template {DEIDENTIFY_TEMPLATE_ID} already exists; skipping.")
        else:
            raise

    print("")
    print("Done. Templates:")
    print(f"  Inspect:    {parent}/inspectTemplates/{INSPECT_TEMPLATE_ID}")
    print(f"  Deidentify: {parent}/deidentifyTemplates/{DEIDENTIFY_TEMPLATE_ID}")


if __name__ == "__main__":
    main()
