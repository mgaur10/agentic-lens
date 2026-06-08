import os
from google.cloud import modelarmor_v1
from google.api_core.client_options import ClientOptions

print("Testing ModelArmorClient...")
try:
    client = modelarmor_v1.ModelArmorClient()
    print("Default transport:", type(client._transport))
    print("Default endpoint:", client._transport._host)
except Exception as e:
    print("Error:", e)

try:
    client_grpc = modelarmor_v1.ModelArmorClient(transport="grpc")
    print("gRPC transport:", type(client_grpc._transport))
    print("gRPC endpoint:", client_grpc._transport._host)
except Exception as e:
    print("gRPC Error:", e)

try:
    client_rest = modelarmor_v1.ModelArmorClient(transport="rest")
    print("REST transport:", type(client_rest._transport))
    print("REST endpoint:", client_rest._transport._host)
except Exception as e:
    print("REST Error:", e)

