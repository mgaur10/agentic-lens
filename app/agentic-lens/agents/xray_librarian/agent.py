"""
X-Ray Librarian — Secure Fetcher.
Loads the root agent from src.librarian (tools + system prompt).
"""
import os
import sys

_pkg_root = os.path.dirname(os.path.abspath(__file__))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)


def _vertex_agent_engine_env_bootstrap() -> None:
    os.environ["GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES"] = "false"
    for _k in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_AI_API_KEY"):
        os.environ.pop(_k, None)
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
    _cur_proj = (os.environ.get("GOOGLE_CLOUD_PROJECT") or "").strip()
    _gcp_id = (os.environ.get("GCP_PROJECT_ID") or "").strip()
    if _gcp_id and (_cur_proj.isdigit() or not _cur_proj):
        os.environ["GOOGLE_CLOUD_PROJECT"] = _gcp_id
    _gcp_loc = (
        os.environ.get("GCP_LOCATION") or os.environ.get("REGION") or "us-west1"
    ).strip()
    _cur_loc = (os.environ.get("GOOGLE_CLOUD_LOCATION") or "").strip()
    if _gcp_loc and (
        not _cur_loc or (_cur_loc == "global" and _gcp_loc != "global")
    ):
        os.environ["GOOGLE_CLOUD_LOCATION"] = _gcp_loc


_vertex_agent_engine_env_bootstrap()


def _early_vertex_init() -> None:
    project = (os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "").strip()
    location = (
        os.environ.get("GCP_LOCATION")
        or os.environ.get("GOOGLE_CLOUD_LOCATION")
        or os.environ.get("REGION")
        or "us-west1"
    ).strip()
    if not project:
        return
    try:
        from vertex_init import init_vertexai
    except ImportError:
        from .vertex_init import init_vertexai
    init_vertexai(project, location)


_early_vertex_init()

try:
    from lens_department_hooks import attach_lens_tracing_to_agent
    from telemetry import init_otel
except ImportError:
    from .lens_department_hooks import attach_lens_tracing_to_agent
    from .telemetry import init_otel

from src.librarian import get_root_agent

init_otel("agentic_lens_xray_librarian")
root_agent = get_root_agent(os.path.join(_pkg_root, "root_agent.yaml"))
attach_lens_tracing_to_agent(
    root_agent,
    span_name="lens.xray.librarian.llm",
    department="xray",
    agent_role="librarian",
)
