#!/usr/bin/env python3
"""
Batch 2: scenarios 11–20 from tests/fixtures/department_scenarios.json (1-based positions).

Run from repo root with env loaded:
  set -a && source .env && set +a
  PYTHONPATH=. agentic-lens/.venv/bin/python scripts/e2e_batch2_ten_scenarios.py

Stops on first CHECK FAIL.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from starlette.testclient import TestClient

_FIXTURE = _REPO / "tests" / "fixtures" / "department_scenarios.json"


def _log(title: str, body: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}\n{body}", flush=True)


def _fail(msg: str) -> None:
    print(f"\n>>> CHECK FAIL: {msg}\n", flush=True)


def _ok(msg: str) -> None:
    print(f"  CHECK OK: {msg}", flush=True)


def _load_batch2_rows() -> list[dict[str, Any]]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    if int(data.get("schema_version", 0)) != 1:
        raise SystemExit("department_scenarios.json schema_version must be 1")
    all_rows: list[dict[str, Any]] = data["scenarios"]
    # 1-based scenarios 11–20 => slice [10:20]
    if len(all_rows) < 20:
        raise SystemExit(f"fixture has only {len(all_rows)} scenarios; need at least 20")
    return all_rows[10:20]


def _checks_for_fixture_row(row: dict[str, Any]) -> tuple[str, ...]:
    exp = row.get("expected_local_department") or ""
    msg = (row.get("message") or "").lower()
    if exp == "Engineering":
        if row.get("engineering_prose_ok"):
            return ("engineering_prose",)
        if "python" in msg or "snippet" in msg:
            return ("engineering_python",)
        return ("engineering_terraform",)
    if exp == "X-Ray":
        return ("xray_generic",)
    if exp == "Events":
        return ("events_rag",)
    if exp == "Chat":
        return ("chat_generic",)
    return ("fixture_department_only",)


def run_checks(
    row: dict[str, Any],
    checks: tuple[str, ...],
    data: dict[str, Any],
) -> Optional[str]:
    log_text = "\n".join(data.get("execution_log") or [])
    ans = (data.get("answer") or "").strip()
    dept = data.get("department")
    ta = (data.get("target_agent") or "").lower()
    want = row.get("expected_local_department")
    min_len = int(row.get("min_answer_len") or 1)

    if data.get("blocked_by_armor") or data.get("guard_blocked"):
        return f"unexpected block (armor={data.get('blocked_by_armor')}, guard={data.get('guard_blocked')})"

    if len(ans) < min_len:
        return f"answer length {len(ans)} < min_answer_len {min_len}"

    if "Routed locally" in log_text or "using local routing fallback" in log_text:
        return "local fallback in log"
    if "AUTH_401" in log_text or "vertex authentication rejected" in log_text.lower():
        return "AUTH_401 / vertex authentication rejected in log"

    if want and dept != want:
        return f"department want {want!r} got {dept!r} (target_agent={data.get('target_agent')!r})"

    if "engineering_terraform" in checks or "engineering_python" in checks:
        if "eng" not in ta:
            return f"target_agent should reference eng, got {data.get('target_agent')!r}"
        ok_pipe = any(
            x in log_text
            for x in (
                "Scout",
                "Coder",
                "Quality and Security Reviewer",
                "Sentinel",
            )
        )
        if not ok_pipe:
            return "missing Scout/Coder/Reviewer pipeline in execution_log"
        low = ans.lower()
        if "engineering_terraform" in checks:
            if "```terraform" not in low and "```hcl" not in low and 'resource "google_' not in ans:
                return "missing Terraform fences / google_ resource in answer"
        if "engineering_python" in checks:
            if "```python" not in low:
                return "missing ```python fence in answer"
        _ok("engineering checks")
        return None

    if "engineering_prose" in checks:
        if "eng" not in ta:
            return f"target_agent should reference eng, got {data.get('target_agent')!r}"
        _ok("engineering prose")
        return None

    if "xray_generic" in checks:
        if "xray" not in ta:
            return f"target_agent should reference xray, got {data.get('target_agent')!r}"
        if "Verification Needed" in ans:
            return "Verification Needed leaked in answer"
        _ok("x-ray")
        return None

    if "events_rag" in checks:
        if "events" not in ta:
            return f"target_agent should reference events, got {data.get('target_agent')!r}"
        low = ans.lower()
        for bad in ("session details:", "don't delete!!", "dont delete!!", "<html"):
            if bad in low:
                return f"Events leak marker: {bad!r}"
        _ok("events")
        return None

    if "chat_generic" in checks:
        if "chat" not in ta:
            return f"target_agent should reference chat, got {data.get('target_agent')!r}"
        _ok("chat")
        return None

    return f"unknown check bundle {checks!r}"


def main() -> int:
    import glass_ui_api

    timeout_s = float(os.environ.get("E2E_BATCH2_TIMEOUT_S", os.environ.get("E2E_BATCH1_TIMEOUT_S", "1200")))
    rows = _load_batch2_rows()

    print(
        f"Batch 2: scenarios 11–20 from {_FIXTURE} ({len(rows)} rows)\n"
        f"Timeout per query: {timeout_s}s",
        flush=True,
    )

    session_id: str | None = None
    with TestClient(glass_ui_api.app) as client:
        for i, row in enumerate(rows, start=11):
            name = row.get("name", "?")
            msg = row.get("message") or ""
            checks = _checks_for_fixture_row(row)
            print("\n" + "#" * 72, flush=True)
            print(f"Scenario {i}/20: {name}", flush=True)
            print(f"expected_local_department={row.get('expected_local_department')!r} checks={checks}", flush=True)
            print("#" * 72, flush=True)

            body: dict[str, Any] = {
                "message": msg,
                "session_id": session_id,
            }
            if "armor_enabled" in row:
                body["armor_enabled"] = row["armor_enabled"]
            else:
                body["armor_enabled"] = False
            if row.get("armor_level"):
                body["armor_level"] = row["armor_level"]

            t0 = time.perf_counter()
            try:
                r = client.post("/api/query", json=body, timeout=timeout_s)
            except Exception as e:
                _fail(f"HTTP/client exception: {e}")
                return 1
            elapsed = time.perf_counter() - t0

            if r.status_code != 200:
                _fail(f"HTTP {r.status_code}: {r.text[:2000]}")
                return 1

            data = r.json()
            session_id = data.get("session_id") or session_id
            dept = data.get("department")
            ans = (data.get("answer") or "").strip()
            elog = data.get("execution_log") or []
            joined = "\n".join(elog)

            _log(
                "Response summary",
                f"status=200  wall_s={elapsed:.1f}\n"
                f"department={dept!r}\n"
                f"target_agent={data.get('target_agent')!r}\n"
                f"blocked_by_armor={data.get('blocked_by_armor')!r} "
                f"guard_blocked={data.get('guard_blocked')!r}\n"
                f"lens_request_id={data.get('lens_request_id')!r}\n"
                f"answer_len={len(ans)}\n",
            )
            _log("execution_log (full)", joined if joined else "(empty)")
            _log("answer preview", (ans[:2500] + ("…" if len(ans) > 2500 else "")) or "(empty)")

            err = run_checks(row, checks, data)
            if err:
                _fail(err)
                print(
                    "\n*** STOPPED ON FIRST FAILURE — paste the blocks above for calibration. ***\n",
                    flush=True,
                )
                return 1
            print(f"Scenario {i} PASSED ({elapsed:.1f}s)", flush=True)

    print("\n>>> BATCH 2: ALL 10 SCENARIOS (11–20) PASSED\n", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
