"""Vertex AI init with explicit ADC and cloud-platform scope (Agent Engine / WIF)."""

import os

_VERTEX_AI_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def init_vertexai(project: str, location: str) -> None:
    os.environ["GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES"] = "false"
    import vertexai

    try:
        from google.auth import default as google_auth_default

        credentials, _ = google_auth_default(scopes=[_VERTEX_AI_SCOPE])
        vertexai.init(project=project, location=location, credentials=credentials)
    except Exception:
        vertexai.init(project=project, location=location)
