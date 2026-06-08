import os
import asyncio
import vertexai
try:
    from vertexai import agent_engines
except ImportError:
    from vertexai.preview import agent_engines

PROJECT_ID = "agentic-ai-lens"
LOCATION = "us-central1"
vertexai.init(project=PROJECT_ID, location=LOCATION)

# Deployed egress test agent ID
id_file_path = os.path.join(os.path.dirname(__file__), "egress_test_agent_id.txt")
if os.path.exists(id_file_path):
    with open(id_file_path, "r") as f:
        engine_id = f.read().strip()
else:
    engine_id = "projects/795375693569/locations/us-central1/reasoningEngines/8563324761340379136"

print(f"Loading Egress Test Agent: {engine_id}...")
engine = agent_engines.get(engine_id)

async def query_agent(url_to_fetch: str):
    prompt = f"Please fetch the URL: {url_to_fetch}"
    print(f"\n=== TESTING FETCH FOR: {url_to_fetch} ===")
    try:
        # Using async_stream_query
        stream = engine.async_stream_query(
            message=prompt,
            user_id="egress_verifier"
        )
        async for ev in stream:
            # Print event chunks as they come
            if isinstance(ev, dict):
                # Print message or event structure
                content = ev.get("content") or ev.get("event") or ev.get("message") or ev
                print(content)
            else:
                # SDK object
                text = getattr(ev, "text", None)
                if text:
                    print(text, end="")
                else:
                    print(ev)
    except Exception as e:
        print(f"\nException caught during query execution: {e}")

async def main():
    # 1. Test an ALLOWED URL (github.com)
    await query_agent("https://github.com")
    
    # 2. Test a BLOCKED URL (wikipedia.org)
    await query_agent("https://wikipedia.org")

asyncio.run(main())
