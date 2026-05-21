"""
Events agent — Conference Concierge.
Uses the RAG tool (retrieve_event_info) to ground answers in the corpus.
"""
import os


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

import yaml
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

try:
    from .src.tools import retrieve_event_info
except ImportError:
    from src.tools import retrieve_event_info

try:
    from lens_department_hooks import attach_lens_tracing_to_agent
    from telemetry import init_otel
except ImportError:
    from .lens_department_hooks import attach_lens_tracing_to_agent
    from .telemetry import init_otel

DEFAULT_MODEL = "gemini-2.5-flash"
_AGENT_YAML = os.path.join(os.path.dirname(__file__), "agent.yaml")


def _load_agent_config() -> dict:
    """Load name, model, description, instruction from agent.yaml."""
    with open(_AGENT_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_root_agent() -> LlmAgent:
    """Build the Concierge LlmAgent with RAG tool and instruction from agent.yaml."""
    data = _load_agent_config()
    return LlmAgent(
        name=data.get("name", "events"),
        description=data.get("description", "Conference Concierge"),
        model=data.get("model", DEFAULT_MODEL),
        instruction=data.get("instruction", ""),
        tools=[FunctionTool(retrieve_event_info)],
    )


# ADK / Vertex Reasoning Engine and Supervisor sub_agents require root_agent to be an LlmAgent
# (or compatible BaseAgent), not a generic wrapper — otherwise resolve_agent_reference fails.
init_otel("agentic_lens_events")
root_agent = _build_root_agent()
attach_lens_tracing_to_agent(
    root_agent,
    span_name="lens.events.llm",
    department="events",
    agent_role="concierge",
)
