import os
from google.cloud import aiplatform

aiplatform.init(project="agentic-ai-lens", location="us-central1")

engine_id = "8862814136560517120"
from vertexai.preview.reasoning_engines import ReasoningEngine
engine = ReasoningEngine(engine_id)
print("Engine Name:", engine.name)
print("Engine Resource Name:", engine.resource_name)
print("gca_resource:")
import pprint
pprint.pprint(engine.gca_resource)
