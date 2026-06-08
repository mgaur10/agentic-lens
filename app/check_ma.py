import os
from google.cloud import modelarmor_v1

client = modelarmor_v1.ModelArmorClient()
parent = "projects/agentic-ai-lens/locations/us-central1"
print(f"Listing templates in {parent}...")
for template in client.list_templates(parent=parent):
    print("Found template:", template.name)
