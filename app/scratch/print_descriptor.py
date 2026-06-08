import os
from google.cloud import aiplatform_v1beta1 as aiplatform

def main():
    try:
        from google.cloud.aiplatform_v1beta1.types import reasoning_engine
        print("ReasoningEngine fields from descriptor:")
        desc = reasoning_engine.ReasoningEngine.DESCRIPTOR
        for field in desc.fields:
            print(f" - {field.name} (type: {field.type})")
            
        print("\nReasoningEngineSpec fields from descriptor:")
        desc_spec = reasoning_engine.ReasoningEngineSpec.DESCRIPTOR
        for field in desc_spec.fields:
            print(f" - {field.name} (type: {field.type})")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
