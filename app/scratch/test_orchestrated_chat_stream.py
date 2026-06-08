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

# Load Deployed Supervisor
supervisor_engine_id = "projects/795375693569/locations/us-central1/reasoningEngines/8862814136560517120"

print(f"Loading Deployed Supervisor Orchestrator: {supervisor_engine_id}...")
engine = agent_engines.get(supervisor_engine_id)

async def test_e2e_chat_routing(user_query: str):
    print(f"\n==================================================")
    print(f"TESTING ORCHESTRATED STREAM FOR: '{user_query}'")
    print(f"==================================================")
    try:
        # In a real production flow, the client queries the supervisor,
        # which parses the intent and hands off to the Chat Engine.
        # By passing 'LENS_STRICT_CHAT_STREAM=true', we ensure the dispatch
        # exclusively runs streamQuery.
        os.environ["LENS_STRICT_CHAT_STREAM"] = "true"
        
        stream = engine.async_stream_query(
            message=user_query,
            user_id="orchestration_verifier"
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
    # This prompt triggers competitor check in Supervisor heuristics, which routes to CHAT.
    # The routed Chat engine is invoked using strict streamQuery dispatch.
    await test_e2e_chat_routing(
        user_query="Hi! I want to learn how to deploy a serverless function on AWS Lambda."
    )

if __name__ == "__main__":
    asyncio.run(main())
