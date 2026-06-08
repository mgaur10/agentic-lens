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

# Live Supervisor Engine ID
supervisor_engine_id = "projects/795375693569/locations/us-central1/reasoningEngines/8862814136560517120"

print(f"Loading Supervisor Agent: {supervisor_engine_id}...")
engine = agent_engines.get(supervisor_engine_id)

async def run_query(prompt: str):
    print(f"\n>>> PROMPT: {prompt}")
    try:
        stream = engine.async_stream_query(
            message=prompt,
            user_id="supervisor_egress_verifier"
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
        print(f"\nException caught: {e}")

async def main():
    # 1. Test an ALLOWED URL via Supervisor routing
    await run_query("Please fetch the contents of this URL and summarize it: https://github.com")
    
    # 2. Test a BLOCKED URL via Supervisor routing
    await run_query("Please fetch the contents of this URL and summarize it: https://wikipedia.org")

asyncio.run(main())
