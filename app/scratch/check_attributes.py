import vertexai
from vertexai import types

print("AgentEngine fields:")
try:
    from vertexai.resources import AgentEngine
    print(AgentEngine.model_fields.keys())
except Exception as e:
    print("Failed to inspect via pydantic model_fields:", e)

try:
    client = vertexai.Client(
        project="agentic-ai-lens",
        location="us-central1",
        http_options=dict(api_version="v1beta1")
    )
    # Let's list agent engines to see what properties they have
    engines = list(client.agent_engines.list())
    if engines:
        engine = engines[0]
        print("First engine object representation:", repr(engine))
        print("First engine attributes:", dir(engine))
        # Print fields if it's a pydantic model
        if hasattr(engine, '__dict__'):
            print("First engine dict keys:", engine.__dict__.keys())
    else:
        print("No deployed engines found.")
except Exception as e:
    print("Error listing engines:", e)
