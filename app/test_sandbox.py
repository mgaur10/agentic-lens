import sys
import os

# Add agent folder to path
sys.path.insert(0, "/usr/local/google/home/manishkgaur/Desktop/Workspace/Agent-gateway/agentic-lens/app/agentic-lens/agents/chat")

try:
    import sitecustomize
    print("Successfully imported sitecustomize!")
    
    # Test the import hook
    import google.cloud.aiplatform.utils.resource_manager_utils as rm_utils
    print("Successfully imported resource_manager_utils via the hook!")
    print("Project ID:", rm_utils.get_project_id())
    print("Project Number:", rm_utils.get_project_number())
except Exception as e:
    print("CRITICAL ERROR:", e)
    import traceback
    traceback.print_exc()
