"""Events stream: suppress function_response.result so UI shows model summary only."""

from __future__ import annotations

from backend.agent_engine_client import _collect_text, _is_events_engine_id


def test_collect_text_omits_tool_result_when_flag_false() -> None:
    ev = {
        "content": {
            "parts": [
                {
                    "function_response": {
                        "response": {"result": "RAW_RAG_SESSION_DETAILS_KEYNOTES_DEVKEY"}
                    }
                },
                {"text": "Here is a concise summary for attendees."},
            ]
        }
    }
    out: list[str] = []
    _collect_text(ev, out, include_function_response_result=False)
    assert "RAW_RAG" not in "\n".join(out)
    assert any("concise summary" in t for t in out)


def test_collect_text_keeps_tool_result_when_flag_true() -> None:
    ev = {
        "content": {
            "parts": [
                {
                    "function_response": {
                        "response": {"result": "TERRAFORM_BLOCK"}
                    }
                },
            ]
        }
    }
    out: list[str] = []
    _collect_text(ev, out, include_function_response_result=True)
    assert "TERRAFORM_BLOCK" in "\n".join(out)


def test_is_events_engine_id_matches_env(monkeypatch) -> None:
    monkeypatch.setenv("EVENTS_ENGINE_ID", "projects/p/locations/us-west1/reasoningEngines/999")
    assert _is_events_engine_id("projects/p/locations/us-west1/reasoningEngines/999")
    assert _is_events_engine_id("reasoningEngines/999")
    assert not _is_events_engine_id("projects/p/locations/us-west1/reasoningEngines/888")


def test_is_events_engine_id_falls_back_to_path_substring() -> None:
    assert _is_events_engine_id("projects/x/locations/l/reasoningEngines/agentic_lens_events_x")
