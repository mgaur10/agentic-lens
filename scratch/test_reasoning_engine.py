import os
import vertexai
try:
    from vertexai.preview.reasoning_engines import ReasoningEngine
except ImportError:
    try:
        from vertexai import agent_engines as ReasoningEngine
    except ImportError:
        from vertexai.preview import agent_engines as ReasoningEngine

project = "agentic-ai-lens"
location = "us-central1"
vertexai.init(project=project, location=location)

print("Calling eng_coder...")
coder = ReasoningEngine("projects/795375693569/locations/us-central1/reasoningEngines/5471603617150533632")
try:
    stream = coder.stream_query(user_id="test", message="Write Terraform for an Autopilot cluster in us-central1")
    for chunk in stream:
        print("CHUNK:", chunk)
except Exception as e:
    print("STREAM FAILED:", e)

print("Calling eng_scout...")
scout = ReasoningEngine("projects/795375693569/locations/us-central1/reasoningEngines/3375177990609567744")
try:
    stream2 = scout.stream_query(user_id="test", message="Write Terraform for an Autopilot cluster in us-central1")
    for chunk in stream2:
        print("CHUNK:", chunk)
except Exception as e:
    print("STREAM FAILED:", e)
