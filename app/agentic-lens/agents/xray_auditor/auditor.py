"""
X-Ray Auditor — Independent QA Gatekeeper.

Mission: Verify the Specialist's output. Do NOT trust; validate.
Tools: Read-only lookup_resource_iam to check the Knowledge Base. No learn tool — the Auditor
only reads, never writes.
"""
import os
from google.adk.agents import LlmAgent
from google.adk.agents.llm_agent_config import LlmAgentConfig
from google.adk.tools import FunctionTool
import yaml

try:
    from src.kb_tools import lookup_resource_iam
except ImportError:
    from kb_tools import lookup_resource_iam

AUDITOR_INSTRUCTION = (
    "You are the Independent QA. You do NOT trust the Specialist. You verify.\n\n"
    "**Validation Protocol:**\n"
    "1. **Existence:** Do these permissions actually exist? (Check the Knowledge Base via "
    "`lookup_resource_iam`)\n"
    "2. **Correctness:** Are the roles correct for the stated purpose?\n"
    "3. **Completeness:** Are there missing permissions?\n"
    "4. **Security Risks:** Are there over-privileged roles?\n\n"
    "Always use the lookup tool to verify claims independently.\n"
    "Output: APPROVED (with brief summary) or REJECTED (with specific issues)."
)


def get_root_agent() -> LlmAgent:
    """Load root agent from YAML config or construct directly."""
    config_path = os.path.join(os.path.dirname(__file__), "root_agent.yaml")
    try:
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        raw = {}
    return LlmAgent(
        name=raw.get("name", "agentic_prism_xray_auditor"),
        model=raw.get("model", "gemini-2.5-pro"),
        description=raw.get("description", "X-Ray Auditor — Independent QA Gatekeeper."),
        instruction=raw.get("instruction", AUDITOR_INSTRUCTION),
        tools=[FunctionTool(lookup_resource_iam)],
    )
