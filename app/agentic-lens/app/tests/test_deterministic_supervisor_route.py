"""Unit tests for client-side deterministic Supervisor routing."""

from __future__ import annotations

import pytest

from backend.agent_engine_client import deterministic_supervisor_route


@pytest.mark.parametrize(
    "message,expected_agent",
    [
        (
            "I am attending Google Cloud Next 2026. Can you find the 'Get real: Agents in the "
            "autonomous era' keynote, tell me the exact time it happens, and give me a brief "
            "summary of what will be covered?",
            "agentic_lens_events",
        ),
        (
            "Can you explain the difference between Google Cloud Sustained Use Discounts (SUDs) "
            "and Committed Use Discounts (CUDs)? When should an enterprise use which?",
            "agentic_lens_chat",
        ),
        (
            "Design a secure architecture for a serverless data ingestion pipeline using "
            "Pub/Sub and Cloud Functions. Write the modular Terraform code for it, and "
            "ensure you use a dedicated least-privilege service account for the function, "
            "not the default compute account.",
            "agentic_lens_eng_lead",
        ),
        (
            "Audit the deployment architecture of this repository and map out its component "
            "topology. I do not need IAM permissions right now, just the architectural "
            "blueprint: https://github.com/dreardon/adk_agentengine_agentspace",
            "agentic_lens_xray_manager",
        ),
    ],
)
def test_four_department_golden_prompts(message: str, expected_agent: str) -> None:
    out = deterministic_supervisor_route(message)
    assert out is not None, f"expected deterministic match for: {message[:80]!r}"
    assert out["target_agent"] == expected_agent
    assert out.get("forwarded_query") == message.strip()
