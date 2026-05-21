"""
Vertex AI + google.genai auth for the Glass backend (Cloud Run / local ADC).

google-genai's load_auth sets GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES=false
when resolving tokens; setting it at process start avoids bound-token 401s on some GCP runtimes.
"""

from __future__ import annotations

import os

_VERTEX_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def ensure_vertex_auth_env() -> None:
    os.environ["GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES"] = "false"


def init_vertexai(project: str, location: str) -> None:
    ensure_vertex_auth_env()
    import vertexai

    try:
        from google.auth import default as google_auth_default

        credentials, _ = google_auth_default(scopes=[_VERTEX_SCOPE])
        vertexai.init(project=project, location=location, credentials=credentials)
    except Exception:
        vertexai.init(project=project, location=location)
