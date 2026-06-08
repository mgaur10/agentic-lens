import os
from google.cloud import modelarmor_v1
from google.protobuf import field_mask_pb2

PROJECT_ID = "agentic-ai-lens"
LOCATION = "us-central1"

client = modelarmor_v1.ModelArmorClient(
    client_options={"api_endpoint": f"modelarmor.{LOCATION}.rep.googleapis.com"}
)

def disable_sdp_for_template(template_id: str):
    template_name = f"projects/{PROJECT_ID}/locations/{LOCATION}/templates/{template_id}"
    print(f"Fetching template {template_name}...")
    template = client.get_template(name=template_name)
    
    # Inspect filter_enforcement current value
    fe = template.filter_config.sdp_settings.basic_config.filter_enforcement
    print(f"  Current filter_enforcement: {fe} (type: {type(fe)})")
    
    # Set to DISABLED (usually 1 or 0 or string name)
    # Let's print the Enum class to see values
    enum_cls = template.filter_config.sdp_settings.basic_config.SdpBasicConfigEnforcement
    print("  Enum class values:")
    for attr in dir(enum_cls):
        if not attr.startswith("_"):
            print(f"    {attr}: {getattr(enum_cls, attr)}")
            
    # Update the field to DISABLED
    template.filter_config.sdp_settings.basic_config.filter_enforcement = enum_cls.DISABLED
    
    # Update template
    update_mask = field_mask_pb2.FieldMask(paths=["filter_config.sdp_settings.basic_config.filter_enforcement"])
    updated_template = client.update_template(
        template=template,
        update_mask=update_mask
    )
    print(f"  Successfully updated template! New value: {updated_template.filter_config.sdp_settings.basic_config.filter_enforcement}")

def main():
    for tid in ["security-high", "security-medium", "test"]:
        try:
            disable_sdp_for_template(tid)
        except Exception as e:
            print(f"Error updating template {tid}: {e}")

if __name__ == "__main__":
    main()
