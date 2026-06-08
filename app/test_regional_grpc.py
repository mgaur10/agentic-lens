import os
from google.cloud import modelarmor_v1
from google.api_core.client_options import ClientOptions

client_options = ClientOptions(api_endpoint="modelarmor.us-central1.rep.googleapis.com")
client = modelarmor_v1.ModelArmorClient(client_options=client_options, transport="grpc")
print("Transport:", type(client._transport))
print("Endpoint:", client._transport._host)

parent = "projects/agentic-ai-lens/locations/us-central1"
template_name = f"{parent}/templates/security-medium"
user_prompt_data = modelarmor_v1.DataItem(text="Hello world")
request = modelarmor_v1.SanitizeUserPromptRequest(
    name=template_name,
    user_prompt_data=user_prompt_data,
)
try:
    response = client.sanitize_user_prompt(request=request)
    print("Success! Response safe:", response.sanitization_result.filter_match_state)
except Exception as e:
    print("Error:", e)
