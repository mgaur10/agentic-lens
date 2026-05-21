"""Pytest setup: repo root on path and isolated Glass UI session state."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture(autouse=True)
def _clear_glass_ui_sessions() -> None:
    import glass_ui_api

    glass_ui_api._sessions.clear()
    yield
    glass_ui_api._sessions.clear()
