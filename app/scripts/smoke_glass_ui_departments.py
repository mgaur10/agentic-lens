#!/usr/bin/env python3
"""
Live E2E: Glass UI /healthz?deep=1 and POST /api/query for department scenarios.

Reads scenarios from tests/fixtures/department_scenarios.json (repo root relative).

Environment:
  IAP_OAUTH_CLIENT_ID  — IAP OAuth client ID (.apps.googleusercontent.com), optional
  GLASS_UI_URL         — Base URL (optional; default Cloud Run URL in code)
  LIVE_E2E_QUERY_TIMEOUT_S — Per-query timeout (default 600)
  LIVE_E2E_HEALTH_TIMEOUT_S — Health check timeout (default 30)

Examples:
  export IAP_OAUTH_CLIENT_ID='...apps.googleusercontent.com'   # optional
  python3 scripts/smoke_glass_ui_departments.py --profile full
  python3 scripts/smoke_glass_ui_departments.py --profile smoke --report /tmp/e2e.json

Rollout order: run `pytest tests/` locally first, then this script against staging/prod.

Troubleshooting: use --report; inspect lens_request_id, execution_log, department, target_agent;
 correlate with Cloud Trace. Full answers in reports are opt-in (--report-full-answers) due to PII.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "department_scenarios.json"

_SUCCESS_MARKERS = (
    "Response received",
    "responded successfully",
    "Direct response returned",
    # Engineering squad (eng lead) uses pipeline step labels, not “Response received”.
    "Engineering Pipeline: Completed successfully",
    "Quality and Security Reviewer: Code approved",
)
_FAIL_ANSWER_SUBSTRINGS = (
    "Empty response from Agent Engine",
    "No Agent Engine is configured",
    "Failed to create session.",
    "No response from Supervisor.",
    "Agent Engine error",
)
_PREVIEW_LEN = 240
_RETRYABLE_HTTP = frozenset({503, 429})
_RETRY_SLEEP_BASE = 2.0


def _fetch_iap_token(audience: str) -> str:
    try:
        import google.oauth2.id_token
        from google.auth.transport.requests import Request
    except ImportError as e:
        print(
            "Missing dependency. Install: pip install google-auth\n"
            f"Import error: {e}",
            file=sys.stderr,
        )
        raise SystemExit(2) from e

    req = Request()
    return google.oauth2.id_token.fetch_id_token(req, audience)


def _load_scenarios(path: Path) -> Tuple[int, List[Dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    ver = int(data.get("schema_version", 0))
    if ver != 1:
        raise SystemExit(f"Unsupported schema_version {ver!r} in {path} (expected 1)")
    scenarios = data.get("scenarios") or []
    if not scenarios:
        raise SystemExit(f"No scenarios in {path}")
    return ver, scenarios


def _filter_profile(rows: List[Dict[str, Any]], profile: str) -> List[Dict[str, Any]]:
    if profile == "full":
        return list(rows)
    if profile == "smoke":
        out = [r for r in rows if "smoke" in (r.get("tags") or [])]
        if not out:
            raise SystemExit(
                'Profile "smoke" requires at least one scenario with "smoke" in tags.'
            )
        return out
    raise SystemExit(f"Unknown profile {profile!r}")


def _http_json(
    url: str,
    method: str,
    headers: Dict[str, str],
    body: Optional[bytes],
    timeout: float,
) -> Tuple[int, Any]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        try:
            payload = e.read().decode("utf-8", errors="replace")
        except Exception:
            payload = ""
        try:
            parsed = json.loads(payload) if payload.strip() else None
        except json.JSONDecodeError:
            parsed = {"detail": payload[:2000]}
        raise _HTTPStatusError(e.code, e.reason, parsed, payload) from e


class _HTTPStatusError(Exception):
    def __init__(
        self,
        code: int,
        reason: str,
        parsed: Any,
        raw: str,
    ) -> None:
        super().__init__(f"HTTP {code} {reason}")
        self.code = code
        self.reason = reason
        self.parsed = parsed
        self.raw = raw


def _with_retries(
    fn,
    retries: int,
    label: str,
) -> Any:
    last_exc: Optional[BaseException] = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except _HTTPStatusError as e:
            last_exc = e
            if e.code not in _RETRYABLE_HTTP or attempt >= retries:
                raise
        except urllib.error.URLError as e:
            last_exc = e
            if attempt >= retries:
                raise
        sleep_s = _RETRY_SLEEP_BASE ** attempt + random.random()
        print(f"  [{label}] retry {attempt + 1}/{retries} after {sleep_s:.1f}s: {last_exc}", flush=True)
        time.sleep(sleep_s)
    raise RuntimeError("unreachable") from last_exc


def _assert_scenario(
    data: Dict[str, Any],
    scenario: Dict[str, Any],
    strict_department: bool,
) -> Optional[str]:
    expect_block = scenario.get("expect_block") is True
    armor_blocked = bool(data.get("blocked_by_armor"))
    guard_blocked = bool(data.get("guard_blocked"))
    log_text = "\n".join(data.get("execution_log") or [])
    ans = (data.get("answer") or "").strip()
    min_len = int(scenario.get("min_answer_len") or 1)

    if expect_block:
        if not armor_blocked and not guard_blocked:
            return "expect_block: expected armor or guard block, got normal response"
        if len(ans) < min_len:
            return f"answer length {len(ans)} < min_answer_len {min_len}"
        for sub in _FAIL_ANSWER_SUBSTRINGS:
            if sub in ans:
                return f"answer contains failure substring {sub!r}"
        if "Routed locally" in log_text or "using local routing fallback" in log_text:
            return "FAIL: Local fallback triggered. Supervisor failed or timed out."
        low_log = log_text.lower()
        if "AUTH_401" in log_text or "vertex authentication rejected" in low_log:
            return "FAIL: Workload Identity / Token sharing rejected by Vertex API."
        return None

    if armor_blocked:
        return "blocked_by_armor is True"
    if guard_blocked:
        return "guard_blocked is True"
    if len(ans) < min_len:
        return f"answer length {len(ans)} < min_answer_len {min_len}"
    for sub in _FAIL_ANSWER_SUBSTRINGS:
        if sub in ans:
            return f"answer contains failure substring {sub!r}"
    if not any(m in log_text for m in _SUCCESS_MARKERS):
        return "execution_log missing success marker"

    if "Routed locally" in log_text or "using local routing fallback" in log_text:
        return "FAIL: Local fallback triggered. Supervisor failed or timed out."
    low_log = log_text.lower()
    if "AUTH_401" in log_text or "vertex authentication rejected" in low_log:
        return "FAIL: Workload Identity / Token sharing rejected by Vertex API."

    dept = data.get("department")
    msg_lower = (scenario.get("message") or "").lower()
    arch_exempt = (
        "architecture" in msg_lower
        or msg_lower.lstrip().startswith("compare ")
        or msg_lower.lstrip().startswith("architect ")
        or scenario.get("engineering_prose_ok") is True
    )
    if dept == "Engineering":
        if not arch_exempt:
            al = ans.lower()
            if (
                "```terraform" not in al
                and "```hcl" not in al
                and "```python" not in al
            ):
                return "FAIL: Engineering response missing fenced code blocks."
    if dept == "X-Ray":
        if "Verification Needed" in ans:
            return "FAIL: X-Ray Sentinel leaked grading rubric into answer."
    if dept == "Events":
        low_ans = ans.lower()
        if (
            "Session Details:" in ans
            or "Don't delete!!" in ans
            or "dont delete!!" in low_ans
            or "<html" in low_ans
        ):
            return "FAIL: Events RAG leaked raw tool output or HTML."

    if strict_department:
        allow = scenario.get("department_allowlist")
        expected = scenario.get("expected_local_department")
        if allow:
            if dept not in allow:
                return f"department {dept!r} not in allowlist {allow!r}"
        elif expected and dept != expected:
            return f"department {dept!r} != expected_local_department {expected!r}"
    return None


def _scenario_result(
    scenario: Dict[str, Any],
    data: Dict[str, Any],
    duration_ms: float,
    full_answers: bool,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    ans = data.get("answer") or ""
    row: Dict[str, Any] = {
        "name": scenario.get("name"),
        "ok": error is None,
        "error": error,
        "duration_ms": round(duration_ms, 2),
        "department": data.get("department"),
        "target_agent": data.get("target_agent"),
        "lens_request_id": data.get("lens_request_id"),
        "blocked_by_armor": data.get("blocked_by_armor"),
        "guard_blocked": data.get("guard_blocked"),
    }
    if full_answers:
        row["answer"] = ans
    else:
        row["answer_preview"] = (ans[:_PREVIEW_LEN] + ("..." if len(ans) > _PREVIEW_LEN else "")) if ans else ""
    logs = data.get("execution_log") or []
    row["execution_log_tail"] = logs[-12:] if isinstance(logs, list) else []
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description="Live Glass UI department E2E")
    ap.add_argument(
        "--profile",
        choices=("smoke", "full"),
        default="full",
        help='Scenario set: "smoke" = tags containing smoke; "full" = all scenarios',
    )
    ap.add_argument(
        "--scenarios",
        type=Path,
        default=_DEFAULT_FIXTURE,
        help="Path to department_scenarios.json",
    )
    ap.add_argument("--report", type=Path, default=None, help="Write JSON summary to this path")
    ap.add_argument(
        "--report-full-answers",
        action="store_true",
        help="Include full answer text in report (PII risk in CI logs)",
    )
    ap.add_argument(
        "--strict-department",
        action="store_true",
        help="Enforce department_allowlist or expected_local_department",
    )
    ap.add_argument(
        "--retries",
        type=int,
        default=0,
        help="Retry count for retryable HTTP errors (503, 429, connection)",
    )
    ap.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first scenario failure (default: run all, exit 1 if any failed)",
    )
    ap.add_argument(
        "--skip-health",
        action="store_true",
        help="Skip /healthz?deep=1 preflight (useful when endpoint is unavailable)",
    )
    args = ap.parse_args()

    client_id = (os.environ.get("IAP_OAUTH_CLIENT_ID") or "").strip()

    base = (os.environ.get("GLASS_UI_URL") or "").strip().rstrip("/")
    if not base:
        base = "https://ai-prism-agent-glass-ui-5f4g2erq4a-uw.a.run.app"

    q_timeout = float((os.environ.get("LIVE_E2E_QUERY_TIMEOUT_S") or "600").strip() or "600")
    h_timeout = float((os.environ.get("LIVE_E2E_HEALTH_TIMEOUT_S") or "30").strip() or "30")

    _, all_rows = _load_scenarios(args.scenarios)
    rows = _filter_profile(all_rows, args.profile)

    headers = {"Content-Type": "application/json"}
    if client_id:
        token = _fetch_iap_token(client_id)
        headers["Authorization"] = f"Bearer {token}"
        print("Auth mode: IAP (Authorization header enabled)", flush=True)
    else:
        print("Auth mode: public (no Authorization header)", flush=True)

    def _health() -> None:
        url = f"{base}/healthz?deep=1"
        status, body = _http_json(url, "GET", headers, None, h_timeout)
        if status != 200:
            raise RuntimeError(f"healthz expected 200, got {status} {body}")
        if isinstance(body, dict) and body.get("status") != "ok":
            raise RuntimeError(f"healthz body not ok: {body}")

    if args.skip_health:
        print("=== healthz?deep=1 skipped ===", flush=True)
    else:
        print("=== healthz?deep=1 ===", flush=True)
        _with_retries(_health, args.retries, "healthz")

    query_url = f"{base}/api/query"
    session_id: Optional[str] = None
    report_rows: List[Dict[str, Any]] = []
    any_fail = False

    for scenario in rows:
        name = scenario.get("name", "?")
        message = scenario.get("message") or ""
        print(f"=== {name} ===", flush=True)
        t0 = time.perf_counter()
        err: Optional[str] = None
        data: Dict[str, Any] = {}

        def _one_query() -> Dict[str, Any]:
            nonlocal session_id
            payload: Dict[str, Any] = {
                "message": message,
                "session_id": session_id,
            }
            if "armor_enabled" in scenario:
                payload["armor_enabled"] = scenario["armor_enabled"]
            else:
                payload["armor_enabled"] = False
            alvl = scenario.get("armor_level")
            if alvl:
                payload["armor_level"] = alvl
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(query_url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=q_timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    parsed = json.loads(raw)
                    session_id = parsed.get("session_id") or session_id
                    return parsed
            except urllib.error.HTTPError as e:
                try:
                    raw = e.read().decode("utf-8", errors="replace")
                except Exception:
                    raw = ""
                if e.code in _RETRYABLE_HTTP:
                    raise _HTTPStatusError(e.code, e.reason or "", None, raw) from e
                raise RuntimeError(f"HTTP {e.code} {e.reason}: {raw[:800]}") from e

        try:
            data = _with_retries(_one_query, args.retries, name)
            err = _assert_scenario(data, scenario, args.strict_department)
        except _HTTPStatusError as e:
            err = f"HTTP {e.code} {e.reason}: {e.raw[:500]!r}"
            data = {}
        except urllib.error.HTTPError as e:
            try:
                raw = e.read().decode("utf-8", errors="replace")
            except Exception:
                raw = ""
            err = f"HTTP {e.code} {e.reason}: {raw[:500]!r}"
        except urllib.error.URLError as e:
            err = f"URLError: {e.reason!r}"
        except Exception as e:
            err = f"{type(e).__name__}: {e}"

        duration_ms = (time.perf_counter() - t0) * 1000
        report_rows.append(_scenario_result(scenario, data, duration_ms, args.report_full_answers, err))

        if err:
            print("FAIL", err, flush=True)
            any_fail = True
            if args.fail_fast:
                break
        else:
            ans = (data.get("answer") or "").strip()
            print("status 200", flush=True)
            print("department", data.get("department"), flush=True)
            print("target_agent", data.get("target_agent"), flush=True)
            print("lens_request_id", data.get("lens_request_id"), flush=True)
            print("preview", ans[:400].replace("\n", " "), flush=True)
            print("answer_len", len(ans), flush=True)
            print("duration_ms", round(duration_ms, 2), flush=True)
        print(flush=True)

    if args.report:
        out = {
            "schema_version": 1,
            "base_url": base,
            "profile": args.profile,
            "strict_department": args.strict_department,
            "scenarios_file": str(args.scenarios),
            "results": report_rows,
            "all_passed": not any_fail,
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"Wrote report {args.report}", flush=True)

    raise SystemExit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
