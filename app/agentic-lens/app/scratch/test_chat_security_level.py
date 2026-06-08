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

# Live Chat Engine ID
chat_engine_id = "projects/795375693569/locations/us-central1/reasoningEngines/8165178406783156224"

print(f"Loading Chat Agent: {chat_engine_id}...")
engine = agent_engines.get(chat_engine_id)

async def run_query():
    print(f"\n>>> PROMPT: 'Hello! Who are you?' with security_level='high'")
    try:
        # Vertex AI SDK stream_query sends **kwargs to the Reasoning Engine container
        stream = engine.stream_query(
            message="Hello! Who are you?",
            user_id="chat_security_level_verifier",
            security_level="high"  # This was throwing the TypeError before!
        )
        for ev in stream:
            print(ev)
        print("\n✅ Query completed successfully!")
    except Exception as e:
        print(f"\n❌ Exception caught: {e}")

if __name__ == "__main__":
    asyncio.run(run_query())
