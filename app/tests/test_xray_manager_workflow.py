"""Regression tests for X-Ray manager repo-audit workflow."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_manager_module():
    root = Path(__file__).resolve().parents[1]
    manager_path = root / "agentic-lens" / "agents" / "xray_manager" / "src" / "manager.py"
    spec = importlib.util.spec_from_file_location("xray_manager_src_manager", manager_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _xray_user_visible_body(manager, response: str) -> str:
    """Strip PRISM_EXECUTION_LOG suffix (Glass does the same for live logs)."""
    start = manager._PRISM_EXEC_LOG_START
    if not response or start not in response:
        return (response or "").strip()
    return response[: response.index(start)].strip()


def test_repo_audit_intent_without_url_uses_pipeline(monkeypatch) -> None:
    manager = _load_manager_module()
    calls: list[tuple[str, str | None]] = []

    def _fake_pipeline(repo_ref: str, session_id=None) -> str:
        calls.append((repo_ref, session_id))
        return "pipeline-result"

    monkeypatch.setattr(manager, "run_analyze_repo_pipeline", _fake_pipeline)

    out = manager.orchestrate_xray("please analyze this repo for least privilege")

    assert _xray_user_visible_body(manager, out) == "pipeline-result"
    assert manager._PRISM_EXEC_LOG_START in out
    assert calls == [("please analyze this repo for least privilege", None)]


def test_repo_topology_blueprint_with_github_uses_analyze_repo_pipeline(monkeypatch) -> None:
    manager = _load_manager_module()
    pipeline_calls: list[tuple[str, str | None]] = []

    def _fake_pipeline(repo_ref: str, session_id=None) -> str:
        pipeline_calls.append((repo_ref, session_id))
        return "## Mock IAM-shaped summary\n- ok"

    monkeypatch.setattr(manager, "run_analyze_repo_pipeline", _fake_pipeline)
    # Blueprint flow tries Librarian → Architect first; force fallback to analyze_repo pipeline.
    monkeypatch.setattr(
        manager,
        "_librarian_fetch_repo_evidence",
        lambda *_a, **_k: "Error: unit test — use IAM-shaped pipeline path",
    )

    q = (
        "Audit the deployment architecture of this repository and map out its component "
        "topology. I do not need IAM permissions right now, just the architectural "
        "blueprint: https://github.com/dreardon/adk_agentengine_agentspace"
    )
    out = manager.orchestrate_xray(q)

    assert "Deployment architecture (from repository evidence)" in out
    assert "## Mock IAM-shaped summary" in out
    assert len(pipeline_calls) == 1
    assert "github.com/dreardon/adk_agentengine_agentspace" in pipeline_calls[0][0]


def test_repo_audit_intent_with_github_url_uses_pipeline_url(monkeypatch) -> None:
    manager = _load_manager_module()
    calls: list[tuple[str, str | None]] = []

    def _fake_pipeline(repo_ref: str, session_id=None) -> str:
        calls.append((repo_ref, session_id))
        return "pipeline-url-result"

    monkeypatch.setattr(manager, "run_analyze_repo_pipeline", _fake_pipeline)

    out = manager.orchestrate_xray("audit https://github.com/acme/demo for IAM")

    assert _xray_user_visible_body(manager, out) == "pipeline-url-result"
    assert manager._PRISM_EXEC_LOG_START in out
    assert calls == [("https://github.com/acme/demo", None)]


def test_non_repo_iam_request_keeps_direct_auditor_path(monkeypatch) -> None:
    manager = _load_manager_module()
    pipeline_calls: list[str] = []
    auditor_calls: list[tuple[str, str, str | None]] = []

    def _fake_pipeline(repo_ref: str, session_id=None) -> str:
        pipeline_calls.append(repo_ref)
        return "unexpected"

    def _fake_route(_query: str) -> str:
        return '"xray_auditor"'

    def _fake_auditor(user_query: str, repo_context: str, session_id=None) -> str:
        auditor_calls.append((user_query, repo_context, session_id))
        return "auditor-result"

    monkeypatch.setattr(manager, "run_analyze_repo_pipeline", _fake_pipeline)
    monkeypatch.setattr(manager, "_route_xray_intent", _fake_route)
    monkeypatch.setattr(manager, "_call_xray_auditor", _fake_auditor)

    out = manager.orchestrate_xray("what permissions do I need for cloud run deploy?")

    assert _xray_user_visible_body(manager, out) == "auditor-result"
    assert manager._PRISM_EXEC_LOG_START in out
    assert pipeline_calls == []
    assert auditor_calls == [("what permissions do I need for cloud run deploy?", "", None)]


def test_collect_from_event_prefers_content_parts_over_top_level_message() -> None:
    """Stream envelopes may put a short status in ``message`` and the real body in ``content.parts``."""
    manager = _load_manager_module()
    out: list[str] = []
    ev = {
        "message": "OK",
        "content": {"parts": [{"text": "Full auditor markdown report here."}]},
    }
    manager._collect_from_event(ev, out)
    assert out == ["Full auditor markdown report here."]


def test_collect_from_event_function_response_result() -> None:
    manager = _load_manager_module()
    out: list[str] = []
    ev = {
        "message": "done",
        "content": {
            "parts": [
                {
                    "function_response": {
                        "response": {"result": "## IAM audit\n- roles/storage.objectViewer"}
                    }
                }
            ]
        },
    }
    manager._collect_from_event(ev, out)
    assert out and "IAM audit" in out[0]


def test_merge_stream_text_chunks_concatenates_token_deltas() -> None:
    manager = _load_manager_module()
    merged = manager._merge_stream_text_chunks(["The ", "minimum ", "IAM "])
    assert merged == "The minimum IAM"


def test_orchestrate_auditor_empty_falls_back_to_specialist(monkeypatch) -> None:
    manager = _load_manager_module()

    def _fake_route(_q: str) -> str:
        return '"xray_auditor"'

    def _fake_auditor(_uq: str, _rc: str, session_id=None) -> str:
        return ""

    def _fake_specialist(payload: str, session_id=None) -> str:
        return "## Answer\nGrant `roles/run.invoker` on the service."

    monkeypatch.setattr(manager, "_route_xray_intent", _fake_route)
    monkeypatch.setattr(manager, "_call_xray_auditor", _fake_auditor)
    monkeypatch.setattr(manager, "_call_specialist", _fake_specialist)
    monkeypatch.setattr(manager, "_extract_github_url", lambda _q: None)

    out = manager.orchestrate_xray("What is the minimum IAM to invoke private Cloud Run?")
    body = _xray_user_visible_body(manager, out)
    assert "roles/run.invoker" in body
    assert "specialist_fallback" in out or "EMPTY_STREAM" in out


def test_orchestrate_auditor_empty_uses_gemini_when_specialist_empty(monkeypatch) -> None:
    manager = _load_manager_module()

    def _fake_route(_q: str) -> str:
        return '"xray_auditor"'

    monkeypatch.setattr(manager, "_route_xray_intent", _fake_route)
    monkeypatch.setattr(manager, "_call_xray_auditor", lambda *_a, **_k: "")
    monkeypatch.setattr(manager, "_call_specialist", lambda *_a, **_k: "")
    monkeypatch.setattr(manager, "_extract_github_url", lambda _q: None)

    def _fake_gem(q: str) -> str:
        return "## IAM\nGrant **`roles/run.invoker`** (permission `run.routes.invoke`) on the Cloud Run **service**."

    monkeypatch.setattr(manager, "_gemini_iam_advisory_fallback", _fake_gem)

    out = manager.orchestrate_xray("Minimum IAM to invoke private Cloud Run?")
    body = _xray_user_visible_body(manager, out)
    assert "roles/run.invoker" in body
    assert "gemini_fallback" in out
