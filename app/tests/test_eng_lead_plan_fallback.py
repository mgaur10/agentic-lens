"""Engineering Lead: when Scout and Gemini plan are empty, Coder still runs (query-only synthetic plan)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_eng_lead_manager():
    root = Path(__file__).resolve().parents[1]
    src = root / "agentic-lens" / "agents" / "eng_lead" / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    manager_path = src / "manager.py"
    spec = importlib.util.spec_from_file_location("eng_lead_src_manager", manager_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_scout_and_gemini_empty_still_invokes_coder_with_synthetic_plan(monkeypatch) -> None:
    mgr = _load_eng_lead_manager()

    monkeypatch.setattr(mgr, "_call_scout", lambda q, session_id=None: "")
    monkeypatch.setattr(mgr, "_plan_fallback_gemini", lambda q: "")
    monkeypatch.setattr(
        mgr,
        "_call_coder",
        lambda prompt, session_id=None: '```terraform\nresource "null_resource" "x" {}\n```',
    )
    monkeypatch.setattr(
        mgr,
        "_call_quality_security_reviewer",
        lambda *a, **k: '{"status": "APPROVED", "reason": "ok"}',
    )

    out = mgr.orchestrate_build("Write Terraform for a test null_resource only.")

    assert "[Scout returned no plan.]" not in out
    assert "PlanFallback_QueryOnly" in out
    assert "null_resource" in out
