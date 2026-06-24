"""Vertex AI init with explicit ADC and cloud-platform scope (Agent Engine / WIF)."""
import os

_VERTEX_AI_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def init_vertexai():
    """Initialize Vertex AI with project and location from environment."""
    import vertexai
    project = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GCP_LOCATION", os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))
    if project:
        vertexai.init(project=project, location=location)
