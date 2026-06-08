"""
X-Ray Librarian — Secure Fetcher agent logic.
Registers tools and system prompt; the Librarian only fetches code context and hands raw text to the Manager.
"""

from __future__ import annotations

import os
from google.adk.agents import LlmAgent
from google.adk.agents.llm_agent_config import LlmAgentConfig

LIBRARIAN_INSTRUCTION = """You are the Librarian. Your ONLY job is to securely fetch code context. You do not analyze it; you just hand the raw text to the Manager.

Use get_repo_contents(repo_url) to list files in a GitHub repo. Use read_file_content(repo_url, file_path) to fetch the raw text of a specific file (e.g. main.tf, cloudbuild.yaml). Return the raw content so the Manager can pass it to downstream agents."""

LIBRARIAN_TOOLS = [
    "src.github_tools.get_repo_contents",
    "src.github_tools.read_file_content",
]

DEFAULT_MODEL = "gemini-2.5-pro"
_ALLOWED_KEYS = frozenset(LlmAgentConfig.model_fields)


def get_root_agent(config_abs_path: str) -> LlmAgent:
    """
    Build the Librarian root agent with Secure Fetcher tools and system prompt.
    config_abs_path: path to root_agent.yaml (used for resolving tool modules).
    """
    raw = {
        "name": "xray_librarian",
        "model": DEFAULT_MODEL,
        "instruction": LIBRARIAN_INSTRUCTION,
        "tools": LIBRARIAN_TOOLS,
    }
    sanitized = {k: v for k, v in raw.items() if k in _ALLOWED_KEYS}
    config = LlmAgentConfig.model_validate(sanitized)
    return LlmAgent.from_config(config.model_dump(mode="json"), config_abs_path)
