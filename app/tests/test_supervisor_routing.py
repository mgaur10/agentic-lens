"""Local supervisor routing vs shared department_scenarios.json expectations."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.supervisor import SupervisorAgent

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "department_scenarios.json"


def _scenarios() -> list[dict]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert data.get("schema_version") == 1
    return data["scenarios"]


def _fixture_routing_pairs() -> list[tuple[str, str]]:
    """Supervisor routing checks only real departments (not Security / block-only rows)."""
    pairs: list[tuple[str, str]] = []
    for s in _scenarios():
        exp = s.get("expected_local_department")
        if (
            not exp
            or exp == "Security"
            or s.get("expect_block")
            or s.get("skip_local_supervisor_assert")
        ):
            continue
        pairs.append((s["message"], exp))
    return pairs


@pytest.mark.parametrize("message,expected", _fixture_routing_pairs())
def test_supervisor_route_matches_fixture(message: str, expected: str) -> None:
    with patch("backend.supervisor.time.sleep"):
        with patch(
            "backend.supervisor_trainer.SupervisorTrainer.suggest_routing",
            return_value=("", 0.0, "test_patch"),
        ):
            agent = SupervisorAgent()
            assert agent.route(message, []) == expected


@pytest.mark.parametrize(
    "message,expected",
    [
        (
            "I am attending Google Cloud Next 2026. Can you find the 'Get real: Agents in "
            "the autonomous era' keynote, tell me the exact time it happens, and give me a "
            "brief summary of what will be covered?",
            "Events",
        ),
        (
            "Can you explain the difference between Google Cloud Sustained Use Discounts "
            "(SUDs) and Committed Use Discounts (CUDs)? When should an enterprise use which?",
            "Chat",
        ),
        (
            "Design a secure architecture for a serverless data ingestion pipeline using "
            "Pub/Sub and Cloud Functions. Write the modular Terraform code for it, and "
            "ensure you use a dedicated least-privilege service account for the function, "
            "not the default compute account.",
            "Engineering",
        ),
        (
            "Audit the deployment architecture of this repository and map out its component "
            "topology. I do not need IAM permissions right now, just the architectural "
            "blueprint: https://github.com/dreardon/adk_agentengine_agentspace",
            "X-Ray",
        ),
    ],
)
def test_supervisor_route_prod_prompts(message: str, expected: str) -> None:
    with patch("backend.supervisor.time.sleep"):
        with patch(
            "backend.supervisor_trainer.SupervisorTrainer.suggest_routing",
            return_value=("", 0.0, "test_patch"),
        ):
            agent = SupervisorAgent()
            assert agent.route(message, []) == expected
