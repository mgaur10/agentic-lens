"""Regression: Vertex session pre-create must work under FastAPI's running event loop."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agent_engine_client import _create_agent_engine_session_sync


@pytest.fixture()
def fake_engine() -> MagicMock:
    eng = MagicMock()
    eng.async_create_session = AsyncMock(return_value={"id": "vertex-session-123"})
    return eng


def test_create_session_sync_from_thread_without_loop(fake_engine: MagicMock) -> None:
    sid = _create_agent_engine_session_sync(fake_engine, "user-a")
    assert sid == "vertex-session-123"
    fake_engine.async_create_session.assert_awaited_once_with(user_id="user-a")


def test_create_session_sync_from_running_loop(fake_engine: MagicMock) -> None:
    """Mirrors /api/query: async route runs sync agent code on a live loop."""

    async def _inner() -> None:
        sid = _create_agent_engine_session_sync(fake_engine, "user-b")
        assert sid == "vertex-session-123"
        fake_engine.async_create_session.assert_awaited_once_with(user_id="user-b")

    asyncio.run(_inner())
