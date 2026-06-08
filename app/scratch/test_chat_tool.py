import os
import sys

# Add agentic-lens/app to path to resolve local module imports
sys.path.insert(0, "/usr/local/google/home/manishkgaur/Desktop/Workspace/Agent-gateway/agentic-lens/app")
sys.path.insert(0, "/usr/local/google/home/manishkgaur/Desktop/Workspace/Agent-gateway/agentic-lens/app/agentic-lens")
sys.path.insert(0, "/usr/local/google/home/manishkgaur/Desktop/Workspace/Agent-gateway/agentic-lens/app/.venv/lib/python3.12/site-packages")

from agents.chat.agent import root_agent

print("Successfully loaded Chat Agent.")
print("Registered Tools:")
for tool in getattr(root_agent, "tools", []):
    print(f" - {getattr(tool, 'name', str(tool))}")

# Query the agent with a prompt that should trigger the tool
prompt = "Please fetch this URL: https://github.com"
print(f"\nTriggering query with prompt: {prompt}")
try:
    response = root_agent.query(prompt)
    print("\nResponse received:")
    print(response)
except Exception as e:
    print(f"Error querying agent: {e}")
