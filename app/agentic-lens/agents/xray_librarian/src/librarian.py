"""
X-Ray Librarian — Secure Fetcher agent logic.
Registers tools and system prompt; the Librarian only fetches code context and hands raw text to the Manager.
"""

from __future__ import annotations

import os
from google.adk.agents import LlmAgent, config_agent_utils
from google.adk.agents.llm_agent_config import LlmAgentConfig

LIBRARIAN_INSTRUCTION = """You are the Librarian. Your ONLY job is to securely fetch code context. You do not analyze it; you just hand the raw text to the Manager.

Use get_repo_contents(repo_url) to list files in a GitHub repo. Use read_file_content(repo_url, file_path) to fetch the raw text of paths the user or Manager asks for (e.g. `*.tf`, `Dockerfile`, `docker-compose.yml`, `cloudbuild.yaml`, `.github/workflows/*.yml`, `app.yaml`, `requirements.txt`, `package.json`, `deploy.py`). Return the raw content so the Manager can pass it to downstream agents.

Hard limits (must follow):
- At most **one** get_repo_contents call per user request unless the first call failed.
- At most **12** read_file_content calls total. If the Manager specifies a lower cap, follow that cap.
- After you have enough deploy/IAM-relevant files, respond in **one** final message with all excerpts concatenated — do not loop or ask follow-up questions."""

LIBRARIAN_TOOLS = [
    "src.github_tools.get_repo_contents",
    "src.github_tools.read_file_content",
]

DEFAULT_MODEL = "gemini-2.5-pro"
_ALLOWED_KEYS = frozenset(LlmAgentConfig.model_fields)


def get_root_agent(config_abs_path: str) -> LlmAgent:
    """Build the Librarian root agent from root_agent.yaml (Agent Engine–compatible loader)."""
    return config_agent_utils.from_config(os.path.abspath(config_abs_path))
