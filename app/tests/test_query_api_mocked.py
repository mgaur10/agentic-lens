"""Mocked POST /api/query — wiring, BLOCK, transient fallback, direct_response, engine_ok false."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

import glass_ui_api
from glass_ui_api import app

_FAKE_MAP = {
    "agentic_lens_supervisor": "projects/fake/locations/fake/reasoningEngines/supervisor",
    "agentic_lens_eng_lead": "projects/fake/locations/fake/reasoningEngines/eng",
    "agentic_lens_xray_manager": "projects/fake/locations/fake/reasoningEngines/xray",
    "agentic_lens_events": "projects/fake/locations/fake/reasoningEngines/events",
    "agentic_lens_chat": "projects/fake/locations/fake/reasoningEngines/chat",
}


def _safe_scan(_prompt: str, _level: str) -> dict:
    return {"safe": True, "template": "off", "armor_summary": "ok"}


def _assert_query_response_shape(data: dict) -> None:
    assert "session_id" in data
    assert "answer" in data and isinstance(data["answer"], str)
    assert "department" in data
    assert "target_agent" in data
    assert "execution_log" in data and isinstance(data["execution_log"], list)
    assert "sources" in data and isinstance(data["sources"], list)
    assert data.get("blocked_by_armor") is False or isinstance(data["blocked_by_armor"], bool)
    assert data.get("guard_blocked") is False or isinstance(data["guard_blocked"], bool)
    assert "session_logs" in data


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _post(client: TestClient, message: str, **patches) -> dict:
    pid = str(uuid.uuid4())
    with patch.multiple(
        glass_ui_api,
        scan_prompt=_safe_scan,
        **patches,
    ):
        r = client.post(
            "/api/query",
            json={
                "message": message,
                "session_id": pid,
                "armor_enabled": False,
            },
        )
    assert r.status_code == 200, r.text
    data = r.json()
    _assert_query_response_shape(data)
    return data


def test_mocked_engineering_hop(client: TestClient) -> None:
    def _route(**_kw):
        return {
            "target_agent": "agentic_lens_eng_lead",
            "forwarded_query": "Write terraform for a bucket",
        }

    def _call(engine_id, **_kw):
        assert "eng" in engine_id
        return ("Terraform resource \"google_storage_bucket\" \"b\" {}", None)

    data = _post(
        client,
        "Write terraform for a bucket",
        is_agent_engine_configured=lambda: True,
        get_engine_id_map=lambda: _FAKE_MAP,
        get_supervisor_routing=_route,
        call_agent_engine=_call,
    )
    assert data["department"] == "Engineering"
    assert data["target_agent"] == "agentic_lens_eng_lead"
    assert "Response received" in "\n".join(data["execution_log"])


def test_mocked_events_hop(client: TestClient) -> None:
    def _route(**_kw):
        return {"target_agent": "agentic_lens_events", "forwarded_query": "When is keynote?"}

    def _call(engine_id, **_kw):
        assert "events" in engine_id
        return ("Keynote is Tuesday.", None)

    data = _post(
        client,
        "When is keynote?",
        is_agent_engine_configured=lambda: True,
        get_engine_id_map=lambda: _FAKE_MAP,
        get_supervisor_routing=_route,
        call_agent_engine=_call,
    )
    assert data["department"] == "Events"
    assert "Response received" in "\n".join(data["execution_log"])


def test_mocked_events_no_hit_appends_rag_pipeline_line(client: TestClient) -> None:
    def _route(**_kw):
        return {"target_agent": "agentic_lens_events", "forwarded_query": "Obscure session XYZ123"}

    def _call(engine_id, **_kw):
        assert "events" in engine_id
        return ("No relevant information found in the corpus.", None)

    with patch.object(glass_ui_api, "log_event") as mock_log:
        data = _post(
            client,
            "Obscure session XYZ123",
            is_agent_engine_configured=lambda: True,
            get_engine_id_map=lambda: _FAKE_MAP,
            get_supervisor_routing=_route,
            call_agent_engine=_call,
        )

    assert data["department"] == "Events"
    assert "No relevant information" in data["answer"]
    assert "Pipeline | RAG | NO_HIT | code=NO_CORPUS_TEXT" in "\n".join(data["execution_log"])
    evt_names = [c.args[0] for c in mock_log.call_args_list if c.args]
    assert "events_rag_no_hit" in evt_names


def test_mocked_xray_hop(client: TestClient) -> None:
    def _route(**_kw):
        return {"target_agent": "agentic_lens_xray_manager", "forwarded_query": "Audit IAM"}

    def _call(engine_id, **_kw):
        assert "xray" in engine_id
        return ("IAM summary OK.", None)

    data = _post(
        client,
        "Audit IAM for my project",
        is_agent_engine_configured=lambda: True,
        get_engine_id_map=lambda: _FAKE_MAP,
        get_supervisor_routing=_route,
        call_agent_engine=_call,
    )
    assert data["department"] == "X-Ray"
    assert "Response received" in "\n".join(data["execution_log"])


def test_mocked_xray_prism_execution_log_stripped_and_merged(client: TestClient) -> None:
    """X-Ray answers must not show PRISM_EXECUTION_LOG; pipeline lines go to execution_log."""

    def _route(**_kw):
        return {"target_agent": "agentic_lens_xray_manager", "forwarded_query": "Audit IAM"}

    prism = (
        "\n\n<!-- PRISM_EXECUTION_LOG -->\n"
        "Pipeline | X-Ray | orchestrate | OK | code=START | msg=manager tool invoked\n"
        "<!-- /PRISM_EXECUTION_LOG -->"
    )

    def _call(engine_id, **_kw):
        assert "xray" in engine_id
        return ("Visible IAM summary only." + prism, None)

    data = _post(
        client,
        "Audit IAM for my project",
        is_agent_engine_configured=lambda: True,
        get_engine_id_map=lambda: _FAKE_MAP,
        get_supervisor_routing=_route,
        call_agent_engine=_call,
    )
    assert data["department"] == "X-Ray"
    assert data["answer"] == "Visible IAM summary only."
    assert "<!-- PRISM_EXECUTION_LOG -->" not in data["answer"]
    log = "\n".join(data["execution_log"])
    assert "Pipeline | X-Ray | orchestrate | OK | code=START" in log


def test_mocked_xray_prism_only_empty_body_gets_fallback_not_empty_engine_message(client: TestClient) -> None:
    """When stream unpack leaves only PRISM lines, UI must not show generic empty-engine text."""

    def _route(**_kw):
        return {"target_agent": "agentic_lens_xray_manager", "forwarded_query": "Audit IAM"}

    prism_only = (
        "<!-- PRISM_EXECUTION_LOG -->\n"
        "Pipeline | X-Ray | auditor | OK | code=OK | msg=response received\n"
        "<!-- /PRISM_EXECUTION_LOG -->"
    )

    def _call(engine_id, **_kw):
        assert "xray" in engine_id
        return (prism_only, None)

    data = _post(
        client,
        "Audit IAM for my project",
        is_agent_engine_configured=lambda: True,
        get_engine_id_map=lambda: _FAKE_MAP,
        get_supervisor_routing=_route,
        call_agent_engine=_call,
    )
    assert data["department"] == "X-Ray"
    assert "Empty response from Agent Engine" not in data["answer"]
    assert "execution steps" in data["answer"].lower()


def test_mocked_xray_prism_empty_peer_failures_hint(client: TestClient) -> None:
    """When PRISM shows peer FAILURES and no answer body, message should not claim 'successful pipeline'."""

    def _route(**_kw):
        return {"target_agent": "agentic_lens_xray_manager", "forwarded_query": "Cloud Run IAM"}

    prism_only = (
        "<!-- PRISM_EXECUTION_LOG -->\n"
        "Pipeline | X-Ray | orchestrate | OK | code=START | msg=manager tool invoked\n"
        "Pipeline | X-Ray | auditor | FAILED | code=EMPTY_STREAM | msg=no text from engine\n"
        "<!-- /PRISM_EXECUTION_LOG -->"
    )

    def _call(engine_id, **_kw):
        assert "xray" in engine_id
        return (prism_only, None)

    data = _post(
        client,
        "What IAM for Cloud Run?",
        is_agent_engine_configured=lambda: True,
        get_engine_id_map=lambda: _FAKE_MAP,
        get_supervisor_routing=_route,
        call_agent_engine=_call,
    )
    assert data["department"] == "X-Ray"
    low = data["answer"].lower()
    assert "peer engines" in low or "xray_manager" in low
    assert "successful pipeline" not in low


def test_mocked_chat_hop(client: TestClient) -> None:
    def _route(**_kw):
        return {"target_agent": "agentic_lens_chat", "forwarded_query": "Hello"}

    def _call(engine_id, **_kw):
        assert "chat" in engine_id
        return ("Hello from chat.", None)

    data = _post(
        client,
        "Hello",
        is_agent_engine_configured=lambda: True,
        get_engine_id_map=lambda: _FAKE_MAP,
        get_supervisor_routing=_route,
        call_agent_engine=_call,
    )
    assert data["department"] == "Chat"
    assert "Response received" in "\n".join(data["execution_log"])


def test_supervisor_block_policy(client: TestClient) -> None:
    def _route(**_kw):
        return {"agent": "BLOCK", "response": "Policy violation: disallowed content"}

    data = _post(
        client,
        "anything",
        is_agent_engine_configured=lambda: True,
        get_engine_id_map=lambda: _FAKE_MAP,
        get_supervisor_routing=_route,
        call_agent_engine=MagicMock(side_effect=AssertionError("engine should not run")),
    )
    assert data["department"] == "Chat"
    assert "Policy violation" in data["answer"]
    assert "Blocked by policy" in "\n".join(data["execution_log"])


def test_supervisor_block_transient_returns_routing_error(client: TestClient) -> None:
    calls: list[str] = []

    def _route(**_kw):
        return {"agent": "BLOCK", "response": "Agent Engine error: supervisor timeout"}

    def _call(engine_id, **_kw):
        calls.append(engine_id)
        return ("Local fallback answer.", None)

    data = _post(
        client,
        "Who are you?",
        is_agent_engine_configured=lambda: True,
        get_engine_id_map=lambda: _FAKE_MAP,
        get_supervisor_routing=_route,
        call_agent_engine=_call,
    )
    assert len(calls) == 0
    assert data["department"] == "Supervisor"
    assert "Routing Error" in data["answer"]
    log = "\n".join(data["execution_log"])
    assert "Step 4 | Supervisor | Routing Error" in log


def test_supervisor_failed_create_session_returns_routing_error(client: TestClient) -> None:
    calls: list[str] = []

    def _route(**_kw):
        return {"agent": "BLOCK", "response": "Agent Engine error: Failed to create session."}

    def _call(engine_id, **_kw):
        calls.append(engine_id)
        return ("IAM summary OK.", None)

    data = _post(
        client,
        "Audit IAM for my project",
        is_agent_engine_configured=lambda: True,
        get_engine_id_map=lambda: _FAKE_MAP,
        get_supervisor_routing=_route,
        call_agent_engine=_call,
    )
    assert len(calls) == 0
    assert data["department"] == "Supervisor"
    assert "Routing Error" in data["answer"]
    assert "Step 4 | Supervisor | Routing Error" in "\n".join(data["execution_log"])


def test_direct_response_no_department_engine(client: TestClient) -> None:
    def _route(**_kw):
        return {"direct_response": "Complete answer from supervisor only."}

    mock_engine = MagicMock(side_effect=AssertionError("department engine should not run"))

    data = _post(
        client,
        "ping",
        is_agent_engine_configured=lambda: True,
        get_engine_id_map=lambda: _FAKE_MAP,
        get_supervisor_routing=_route,
        call_agent_engine=mock_engine,
    )
    assert data["department"] == "Supervisor"
    assert data["answer"] == "Complete answer from supervisor only."
    log = "\n".join(data["execution_log"])
    assert "Direct response returned" in log
    assert "Response received" not in log


def test_engine_ok_false_returns_engine_unavailable(client: TestClient) -> None:
    remote = MagicMock(side_effect=AssertionError("get_supervisor_routing must not run"))

    def _call(engine_id, **_kw):
        return ("Chat local synthetic.", None)

    data = _post(
        client,
        "Who are you?",
        is_agent_engine_configured=lambda: False,
        get_engine_id_map=lambda: _FAKE_MAP,
        get_supervisor_routing=remote,
        call_agent_engine=_call,
    )
    assert remote.call_count == 0
    assert data["department"] == "Supervisor"
    assert "Agent Engine is offline or not configured" in data["answer"]
    assert "Engine unavailable" in "\n".join(data["execution_log"])
