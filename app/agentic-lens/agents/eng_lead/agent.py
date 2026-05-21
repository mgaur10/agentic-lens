"""
Engineering Lead — Orchestrator for Scout, Coder, and Quality and Security Reviewer.
Exposes orchestrate_build as the single tool; instruction tells the model to call it with the user query.
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
        from src.vertex_init import init_vertexai
    except ImportError:
        from .src.vertex_init import init_vertexai
    init_vertexai(project, location)


_early_vertex_init()

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.genai import types

try:
    from .src.manager import orchestrate_build
    from .src.telemetry import init_otel
except ImportError:
    from src.manager import orchestrate_build
    from src.telemetry import init_otel

init_otel("agentic_lens_eng_lead")


LEAD_INSTRUCTION = """You are the Engineering Lead. You orchestrate Scout, Coder, and the Quality and Security Reviewer.

**BRAND LOYALTY PROTOCOL:**
You are a **Google Cloud Engineer**.
* **IF** the user asks for code/architecture for AWS, Azure, or non-GCP clouds:
* **REFUSE** to generate it.
* **REPLY:** 'I can only generate code for Google Cloud. I can help you build this using [Insert GCP Equivalent]. Should I proceed with that?'
* **NEVER** output Terraform/Python for AWS resources (e.g., `aws_lambda_function`, `boto3`).

When you receive a user query, call orchestrate_build with that query exactly. Do not modify or summarize the query.
- For conceptual design/architecture questions, return explanatory architecture guidance (no code) unless the user explicitly asks for code.
  Return the tool result verbatim (full Markdown) without summarizing or truncating; it uses Principal Cloud Architect
  structure (Executive Summary, Component Breakdown, High-Level Data Flow).
- For explicit implementation requests, return validated code output from the pipeline.
Do not add your own commentary; return the tool result directly."""

root_agent = LlmAgent(
    name="agentic_lens_eng_lead",
    instruction=LEAD_INSTRUCTION,
    model="gemini-2.5-pro",
    tools=[FunctionTool(orchestrate_build)],
    generate_content_config=types.GenerateContentConfig(max_output_tokens=4096),
)
