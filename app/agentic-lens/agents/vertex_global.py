"""
Shared helper for Engineering agents: Vertex AI models with vertex_location="global".
Use this to work around regional endpoint issues for gemini-2.5-pro / gemini-2.5-flash.
"""
from google.adk.models import LiteLlm


def get_vertex_llm(model_name: str):
    """Return a LiteLlm instance for the given model using the global Vertex endpoint."""
    return LiteLlm(f"vertex_ai/{model_name}", vertex_location="global")
