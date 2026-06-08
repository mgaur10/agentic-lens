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

# Deployed Chat Agent ID
engine_id = "projects/795375693569/locations/us-central1/reasoningEngines/8165178406783156224"

print(f"Loading Deployed Chat Agent: {engine_id}...")
engine = agent_engines.get(engine_id)

async def query_agent(url_to_fetch: str):
    prompt = f"Please fetch the contents of this URL and summarize it: {url_to_fetch}"
    print(f"\n=== TESTING CHAT FETCH FOR: {url_to_fetch} ===")
    try:
        stream = engine.async_stream_query(
            message=prompt,
            user_id="chat_egress_verifier"
        )
        async for ev in stream:
            if isinstance(ev, dict):
                content = ev.get("content") or ev.get("event") or ev.get("message") or ev
                print(content)
            else:
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
