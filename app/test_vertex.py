import sys
from google.cloud import aiplatform

aiplatform.init(project='agentic-ai-lens', location='us-central1')
try:
    engine = aiplatform.ReasoningEngine('8165178406783156224')
    print("Calling Reasoning Engine...")
    response = engine.query(input="Hello, this is a smoke test to trigger llm_usage telemetry. Please reply with 'Acknowledged'.")
    print(f"Response: {response}")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
