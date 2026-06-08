import os
import asyncio
import vertexai
try:
    from vertexai import agent_engines
except ImportError:
    from vertexai.preview import agent_engines

project = "agentic-security-dev"
location = "us-central1"
vertexai.init(project=project, location=location)

engine_id = "projects/504643566830/locations/us-central1/reasoningEngines/5256389609176170496"
print("Getting agent engine via agent_engines.get...")
engine = agent_engines.get(engine_id)

user_query = "Perform a comprehensive security audit on this repository. What IAM permissions are required?"

async def run_async():
    print("Querying xray_manager reasoning engine via async_stream_query...")
    asq = getattr(engine, "async_stream_query", None)
    if not asq:
        print("Error: async_stream_query not found on engine object.")
        return
    try:
        stream = asq(
            message=user_query,
            user_id="test_user",
            session_id="test_session"
        )
        print("Async Events stream received:")
        async for ev in stream:
            print("Event:", ev)
    except Exception as e:
        print("Error during async stream:", e)

asyncio.run(run_async())
