#!/usr/bin/env python3
import sys

def check_version(v):
    print(f"\n=== Checking google.cloud.aiplatform_{v} ===")
    try:
        mod = __import__(f"google.cloud.aiplatform_{v}", fromlist=["types"])
        ReasoningEngine = mod.types.ReasoningEngine
        
        # Print descriptor fields
        print("ReasoningEngine fields from descriptor:")
        for field in ReasoningEngine.pb().DESCRIPTOR.fields:
            print(f" - {field.name}: {field.type}")
            
        print("\nReasoningEngineSpec fields from descriptor:")
        ReasoningEngineSpec = mod.types.ReasoningEngineSpec
        for field in ReasoningEngineSpec.pb().DESCRIPTOR.fields:
            print(f" - {field.name}: {field.type}")
            
        print("\nReasoningEngineSpec.DeploymentSpec fields from descriptor:")
        DeploymentSpec = ReasoningEngineSpec.pb().DESCRIPTOR.nested_types[0] # Try nested type
        # Or check if DeploymentSpec type is defined directly
        try:
            DeploymentSpec = mod.types.ReasoningEngineSpec.DeploymentSpec
            for field in DeploymentSpec.pb().DESCRIPTOR.fields:
                print(f" - {field.name}: {field.type}")
        except Exception as e_nested:
            print("  Could not get DeploymentSpec direct class:", e_nested)
            
        # Check if ReasoningEngine has agent_gateway_config or client_to_agent_config or similar
        print("\nChecking for any gateway/client properties on classes...")
        for name in dir(ReasoningEngine):
            if "gateway" in name.lower() or "client" in name.lower():
                print(f" - ReasoningEngine.{name}")
        for name in dir(ReasoningEngineSpec):
            if "gateway" in name.lower() or "client" in name.lower():
                print(f" - ReasoningEngineSpec.{name}")
    except Exception as e:
        print(f"Error checking version {v}: {e}")

def main():
    check_version("v1alpha")
    check_version("v1beta1")
    check_version("v1")

if __name__ == "__main__":
    main()
