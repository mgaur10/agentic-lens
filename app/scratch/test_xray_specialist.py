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

# Live xray_specialist Engine ID
xray_specialist_engine_id = "projects/795375693569/locations/us-central1/reasoningEngines/4512759108985683968"

print(f"Loading xray_specialist Agent: {xray_specialist_engine_id}...")
engine = agent_engines.get(xray_specialist_engine_id)

async def run_query(prompt: str):
    print(f"\n>>> PROMPT: {prompt}")
    try:
        stream = engine.async_stream_query(
            message=prompt,
            user_id="xray_specialist_tester"
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
        print()
    except Exception as e:
        print(f"\nException caught: {e}")

async def main():
    await run_query("Hi, can you help me audit permissions for a GCS bucket?")

asyncio.run(main())
