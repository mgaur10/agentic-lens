#!/usr/bin/env python3
"""
Create Model Armor security templates (security-medium, security-high) via Python API.
Matches the settings from setup_model_armor_templates.sh.
Usage: python create_model_armor_templates.py [PROJECT_ID] [LOCATION]
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


def main():
    from google.api_core.client_options import ClientOptions
    from google.cloud import modelarmor_v1
    from google.cloud.modelarmor_v1.types import (
        CreateTemplateRequest,
        Template,
        FilterConfig,
        RaiFilterSettings,
        PiAndJailbreakFilterSettings,
        MaliciousUriFilterSettings,
        SdpFilterSettings,
        SdpBasicConfig,
        RaiFilterType,
        DetectionConfidenceLevel,
    )

    parent = f"projects/{PROJECT_ID}/locations/{LOCATION}"
    client = modelarmor_v1.ModelArmorClient(
        transport="rest",
        client_options=ClientOptions(api_endpoint=f"modelarmor.{LOCATION}.rep.googleapis.com"),
    )

    # --- security-medium: All RAI filters (Hate, Harassment, Sexually Explicit, Dangerous) MEDIUM_AND_ABOVE; PI/jailbreak + malicious URI ---
    rai_medium = RaiFilterSettings(
        rai_filters=[
            RaiFilterSettings.RaiFilter(filter_type=RaiFilterType.HATE_SPEECH, confidence_level=DetectionConfidenceLevel.MEDIUM_AND_ABOVE),
            RaiFilterSettings.RaiFilter(filter_type=RaiFilterType.HARASSMENT, confidence_level=DetectionConfidenceLevel.MEDIUM_AND_ABOVE),
            RaiFilterSettings.RaiFilter(filter_type=RaiFilterType.SEXUALLY_EXPLICIT, confidence_level=DetectionConfidenceLevel.MEDIUM_AND_ABOVE),
            RaiFilterSettings.RaiFilter(filter_type=RaiFilterType.DANGEROUS, confidence_level=DetectionConfidenceLevel.MEDIUM_AND_ABOVE),
        ]
    )
    pi_medium = PiAndJailbreakFilterSettings(
        filter_enforcement=PiAndJailbreakFilterSettings.PiAndJailbreakFilterEnforcement.ENABLED,
        confidence_level=DetectionConfidenceLevel.MEDIUM_AND_ABOVE,
    )
    uri_enabled = MaliciousUriFilterSettings(
        filter_enforcement=MaliciousUriFilterSettings.MaliciousUriFilterEnforcement.ENABLED
    )

    filter_config_medium = FilterConfig(
        rai_settings=rai_medium,
        pi_and_jailbreak_filter_settings=pi_medium,
        malicious_uri_filter_settings=uri_enabled,
    )
    template_medium = Template(filter_config=filter_config_medium)

    print("Creating template: security-medium...")
    req_medium = CreateTemplateRequest(
        parent=parent,
        template_id="security-medium",
        template=template_medium,
    )
    try:
        created_medium = client.create_template(request=req_medium)
        print("  Created:", created_medium.name)
    except Exception as e:
        print("  FAILED:", e)
        if "already exists" in str(e).lower():
            print("  (Template may already exist; continuing.)")
        else:
            raise

    # --- security-high (High+DLP): All RAI filters LOW_AND_ABOVE (Strict), PI/jailbreak, malicious URI, SDP ---
    # SDP basic redaction (common PII). For CREDIT_CARD_NUMBER and US_SOCIAL_SECURITY_NUMBER
    # explicitly, use SdpAdvancedConfig with DLP inspect/deidentify templates (see update_model_armor_templates.py).
    rai_high = RaiFilterSettings(
        rai_filters=[
            RaiFilterSettings.RaiFilter(filter_type=RaiFilterType.HATE_SPEECH, confidence_level=DetectionConfidenceLevel.LOW_AND_ABOVE),
            RaiFilterSettings.RaiFilter(filter_type=RaiFilterType.HARASSMENT, confidence_level=DetectionConfidenceLevel.LOW_AND_ABOVE),
            RaiFilterSettings.RaiFilter(filter_type=RaiFilterType.SEXUALLY_EXPLICIT, confidence_level=DetectionConfidenceLevel.LOW_AND_ABOVE),
            RaiFilterSettings.RaiFilter(filter_type=RaiFilterType.DANGEROUS, confidence_level=DetectionConfidenceLevel.LOW_AND_ABOVE),
        ]
    )
    pi_high = PiAndJailbreakFilterSettings(
        filter_enforcement=PiAndJailbreakFilterSettings.PiAndJailbreakFilterEnforcement.ENABLED,
        confidence_level=DetectionConfidenceLevel.LOW_AND_ABOVE,
    )
    sdp_basic = SdpFilterSettings(
        basic_config=SdpBasicConfig(
            filter_enforcement=SdpBasicConfig.SdpBasicConfigEnforcement.ENABLED
        )
    )

    filter_config_high = FilterConfig(
        rai_settings=rai_high,
        pi_and_jailbreak_filter_settings=pi_high,
        malicious_uri_filter_settings=uri_enabled,
        sdp_settings=sdp_basic,
    )
    template_high = Template(filter_config=filter_config_high)

    print("Creating template: security-high...")
    req_high = CreateTemplateRequest(
        parent=parent,
        template_id="security-high",
        template=template_high,
    )
    try:
        created_high = client.create_template(request=req_high)
        print("  Created:", created_high.name)
    except Exception as e:
        print("  FAILED:", e)
        if "already exists" in str(e).lower():
            print("  (Template may already exist; continuing.)")
        else:
            raise

    print("")
    print("Done. Templates:")
    print(f"  - {parent}/templates/security-medium")
    print(f"  - {parent}/templates/security-high")


if __name__ == "__main__":
    main()
