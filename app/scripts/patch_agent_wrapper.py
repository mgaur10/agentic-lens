import sys
import glob

WRAPPER_CODE = """

# --- Vertex Gateway Wrapper ---
# Bypasses the Vertex AI 1.75.0 LlmAgent session memory interceptor
# to explicitly expose 'query' and 'stream_query' for the gateway API.
class VertexGatewayWrapper:
    def __init__(self, agent):
        self._agent = agent
        
    def set_up(self):
        if hasattr(self._agent, "set_up"):
            self._agent.set_up()
            
    def query(self, message: str, session_id: str = None, **kwargs) -> str:
        if hasattr(self._agent, "query"):
            return self._agent.query(message=message, session_id=session_id, **kwargs)
        # Fallback if agent doesn't have query
        return self._agent(message)
        
    def stream_query(self, message: str, session_id: str = None, **kwargs):
        if hasattr(self._agent, "stream_query"):
            for chunk in self._agent.stream_query(message=message, session_id=session_id, **kwargs):
                yield chunk
        else:
            yield self.query(message=message, session_id=session_id, **kwargs)

# Wrap the root agent so Vertex AI introspection sees standard methods
if 'root_agent' in locals() and not isinstance(root_agent, VertexGatewayWrapper):
    root_agent = VertexGatewayWrapper(root_agent)
"""

def main():
    agent_files = glob.glob("agentic-lens/agents/*/agent.py")
    for fpath in agent_files:
        with open(fpath, "r") as f:
            content = f.read()
            
        if "VertexGatewayWrapper" not in content:
            with open(fpath, "a") as f:
                f.write(WRAPPER_CODE)
            print(f"Patched {fpath} with VertexGatewayWrapper.")

if __name__ == "__main__":
    main()
