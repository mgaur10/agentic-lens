import os
import sys

# Add extra_pkgs to path
sys.path.insert(0, "/usr/local/google/home/manishkgaur/Desktop/Workspace/Agent-gateway/extra_pkgs")

from google.adk.integrations.agent_registry.agent_registry import AgentRegistry

project = "agentic-ai-lens"
location = "us-central1"

print(f"Interrogating Agent Registry for {project} in {location}...")
registry = AgentRegistry(project_id=project, location=location)

try:
    print("\n--- MCP SERVERS ---")
    mcp_servers = registry.list_mcp_servers()
    print(mcp_servers)
except Exception as e:
    print(f"Error listing MCP servers: {e}")

try:
    print("\n--- ENDPOINTS ---")
    endpoints = registry.list_endpoints()
    print(endpoints)
except Exception as e:
    print(f"Error listing endpoints: {e}")

try:
    print("\n--- AGENTS ---")
    agents = registry.list_agents()
    print(agents)
except Exception as e:
    print(f"Error listing agents: {e}")
