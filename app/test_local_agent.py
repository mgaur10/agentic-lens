import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "agentic-lens/agents/chat")))

os.environ["PYTHONHTTPSVERIFY"] = "0"
os.environ["GOOGLE_CLOUD_PROJECT"] = "agentic-ai-lens"
os.environ["VERTEX_AI_PROJECT"] = "agentic-ai-lens"
os.environ["VERTEX_AI_LOCATION"] = "us-central1"

import agent
from google.adk.runners import Runner
import logging
logging.basicConfig(level=logging.INFO)

async def main():
    try:
        root_agent = agent.root_agent
        runner = Runner(agent=root_agent)
        print("Running chat agent locally...")
        response_stream = runner.run_async(user_id="test_user", session_id="test_session", new_message="Say hello", run_config={})
        async for event in response_stream:
            print(event)
        print("Done!")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
