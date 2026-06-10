import os
import glob

# Resolve paths relative to this script, not the working directory
# This script lives at: agentic-lens/app/scripts/patch_agent_wrapper.py
# Agents live at:       agentic-lens/app/agentic-lens/agents/*/agent.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AGENTS_DIR = os.path.join(SCRIPT_DIR, "..", "agentic-lens", "agents")

WRAPPER_CODE = """

# --- Vertex Gateway Wrapper ---
# Bypasses the Vertex AI 1.75.0 LlmAgent session memory interceptor
# to explicitly expose 'query' and 'stream_query' for the gateway API.
# A plain Python class (not LlmAgent subclass) causes Vertex AI to use
# standard method discovery instead of forcing the session memory wrapper.
class VertexGatewayWrapper:
    def __init__(self, agent):
        self._agent = agent

    def set_up(self):
        if hasattr(self._agent, "set_up"):
            self._agent.set_up()

    def query(self, message: str, session_id: str = None, **kwargs) -> str:
        if hasattr(self._agent, "query"):
            return self._agent.query(message=message, session_id=session_id, **kwargs)
        return str(self._agent(message))

    def stream_query(self, message: str, session_id: str = None, **kwargs):
        if hasattr(self._agent, "stream_query"):
            for chunk in self._agent.stream_query(message=message, session_id=session_id, **kwargs):
                yield chunk
        else:
            yield self.query(message=message, session_id=session_id, **kwargs)

# Wrap the root agent so Vertex AI introspection sees standard methods
if 'root_agent' in dir() and not isinstance(root_agent, VertexGatewayWrapper):
    root_agent = VertexGatewayWrapper(root_agent)
"""

def main():
    pattern = os.path.join(AGENTS_DIR, "*", "agent.py")
    agent_files = glob.glob(pattern)
    print(f"[patch_agent_wrapper] Scanning: {pattern}")
    print(f"[patch_agent_wrapper] Found {len(agent_files)} agent files: {agent_files}")

    if not agent_files:
        print("[patch_agent_wrapper] WARNING: No agent files found — check AGENTS_DIR path!")
        print(f"[patch_agent_wrapper] SCRIPT_DIR={SCRIPT_DIR}")
        print(f"[patch_agent_wrapper] AGENTS_DIR resolved to: {os.path.realpath(AGENTS_DIR)}")
        return

    for fpath in agent_files:
        with open(fpath, "r") as f:
            content = f.read()

        if "VertexGatewayWrapper" not in content:
            with open(fpath, "a") as f:
                f.write(WRAPPER_CODE)
            print(f"[patch_agent_wrapper] ✅ Patched: {fpath}")
        else:
            print(f"[patch_agent_wrapper] ⏭  Already patched: {fpath}")

if __name__ == "__main__":
    main()
