"""Regression: empty sync stream_query should fall back to async_stream_query (ADK remote engines)."""

from __future__ import annotations

from backend.agent_engine_client import _collect_agent_engine_stream_events, _stream_query_with_timeout


def test_collect_uses_async_when_sync_yields_nothing() -> None:
    class _Eng:
        def stream_query(self, **kwargs):
            return iter([])

        async def async_stream_query(self, **kwargs):
            yield {"content": {"parts": [{"text": "from-async"}]}}

    out = _collect_agent_engine_stream_events(
        _Eng(), {"message": "hi", "user_id": "u1"}
    )
    assert len(out) == 1
    assert "from-async" in str(out[0])


def test_collect_sync_only_when_it_yields() -> None:
    class _Eng:
        def stream_query(self, **kwargs):
            yield {"content": {"parts": [{"text": "sync"}]}}

        async def async_stream_query(self, **kwargs):
            yield {"content": {"parts": [{"text": "should-not-run"}]}}

    out = _collect_agent_engine_stream_events(
        _Eng(), {"message": "hi", "user_id": "u1"}
    )
    assert len(out) == 1
    assert "sync" in str(out[0])
    assert "should-not-run" not in str(out[0])


def test_stream_query_with_timeout_runs_async_fallback_in_worker_thread() -> None:
    class _Eng:
        def stream_query(self, **kwargs):
            return iter([])

        async def async_stream_query(self, **kwargs):
            yield {"t": 1}

    events, timed_out = _stream_query_with_timeout(
        _Eng(), {"message": "m", "user_id": "u"}, timeout_s=30
    )
    assert not timed_out
    assert len(events) == 1
