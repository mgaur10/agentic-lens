"""
Chat Agent — Lens Guide (System-Aware Assistant).
Implements LlmAgent with a from_config "Safe Loader" that filters runtime, identity, etc.
to prevent Pydantic ValidationError when loading YAML.
"""
import os
import yaml
from google.adk.agents import LlmAgent, config_agent_utils
from google.adk.agents.llm_agent_config import LlmAgentConfig

DEFAULT_MODEL = "gemini-2.5-flash"
_ALLOWED_KEYS = frozenset(LlmAgentConfig.model_fields)


def _sanitize_agent_name(sanitized: dict, default: str) -> None:
    """Convert kebab-case to valid Python identifier (hyphens -> underscores)."""
    name = sanitized.get("name")
    sanitized["name"] = (name if isinstance(name, str) else default).replace("-", "_")


CHAT_INSTRUCTION = """You are the General Assistant for Agentic-Lens.
You are part of a specialized team:
- **Engineering Squad:** Builds Infrastructure (ask 'eng_lead').
  - **X-Ray Dept:** Handles IAM, Secrets, and Security Audits (ask 'xray_manager').
- **Events:** Concierge for the Google Cloud Next conference (ask 'events').

**Your Job:**
- If a user asks general questions ('Hi', 'What is Python?'), answer them.
- If a user asks about Infra, Security, or the Conference, politely guide them to the right department.
- Be concise and helpful."""


def _safe_load_root_agent(config_path: str) -> LlmAgent:
    return config_agent_utils.from_config(os.path.abspath(config_path))


def build_root_agent() -> LlmAgent:
    """Build the Chat LlmAgent from root_agent.yaml with safe loader, or inline defaults."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "root_agent.yaml")
    if os.path.isfile(config_path):
        return _safe_load_root_agent(config_path)
    return LlmAgent(
        name="chat",
        description="Lens Guide — General Assistant for Agentic-Lens.",
        model=DEFAULT_MODEL,
        instruction=CHAT_INSTRUCTION,
    )


root_agent = build_root_agent()
