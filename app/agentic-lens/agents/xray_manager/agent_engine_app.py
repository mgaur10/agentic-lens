import os
import vertexai
from vertexai.agent_engines import AdkApp
from agent import root_agent  # top-level import (PYTHONPATH = /code/xray_manager_staged)

vertexai.init(
    project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
    location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
)

adk_app = AdkApp(
    agent=root_agent,
    enable_tracing=True,
)
