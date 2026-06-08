#!/usr/bin/env python3
"""
Run four department E2E prompts against glass_ui_api (same stack as production).

Usage (from repo root):
  set -a && source .env && set +a
  agentic-lens/.venv/bin/python scripts/e2e_four_departments.py

Env: uses .env already exported in shell (GCP, engine IDs).
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from starlette.testclient import TestClient


def _fail(msg: str) -> None:
    print(f"  CHECK FAIL: {msg}", flush=True)


def _ok(msg: str) -> None:
    print(f"  CHECK OK: {msg}", flush=True)


def main() -> int:
    import glass_ui_api

    print(
        "E2E: four departments — Events (no HTML/GTM echo), Chat (consultative), "
        "Engineering (Scout→Coder→Sentinel + Terraform fences), "
        "X-Ray (topology blueprint, no local routing, no Verification Needed leak).",
        flush=True,
    )

    scenarios: list[dict[str, Any]] = [
        {
            "name": "Events (Concierge)",
            "message": (
                "I am attending Google Cloud Next 2026. Can you find the "
                "'Get real: Agents in the autonomous era' keynote, tell me the exact time "
                "it happens, and give me a brief summary of what will be covered?"
            ),
            "expect_department": "Events",
        },
        {
            "name": "Chat (Ambassador — SUDs vs CUDs)",
            "message": (
                "Can you explain the difference between Google Cloud Sustained Use Discounts (SUDs) "
                "and Committed Use Discounts (CUDs)? When should an enterprise use which?"
            ),
            "expect_department": "Chat",
        },
        {
            "name": "Engineering (Pub/Sub + Cloud Functions Terraform)",
            "message": (
                "Design a secure architecture for a serverless data ingestion pipeline using "
                "Pub/Sub and Cloud Functions. Write the modular Terraform code for it, and ensure "
                "you use a dedicated least-privilege service account for the function, not the "
                "default compute account."
            ),
            "expect_department": "Engineering",
        },
        {
            "name": "X-Ray (topology blueprint — dreardon repo)",
            "message": (
                "Audit the deployment architecture of this repository and map out its component "
                "topology. I do not need IAM permissions right now, just the architectural blueprint: "
                "https://github.com/dreardon/adk_agentengine_agentspace"
            ),
            "expect_department": "X-Ray",
        },
    ]

    timeout_s = float(os.environ.get("E2E_FOUR_TIMEOUT_S", "1200"))
    print(f"Timeout per query: {timeout_s}s", flush=True)

    any_hard_fail = False
    with TestClient(glass_ui_api.app) as client:
        session_id: str | None = None
        for sc in scenarios:
            name = sc["name"]
            msg = sc["message"]
            want_dept = sc["expect_department"]
            print("\n" + "=" * 72, flush=True)
            print(name, flush=True)
            print("=" * 72, flush=True)
            t0 = time.perf_counter()
            body = {
                "message": msg,
                "session_id": session_id,
                "armor_enabled": False,
            }
            try:
                r = client.post(
                    "/api/query",
                    json=body,
                    timeout=timeout_s,
                )
            except Exception as e:
                print(f"HTTP EXCEPTION: {e}", flush=True)
                any_hard_fail = True
                continue
            elapsed = time.perf_counter() - t0
            print(f"status={r.status_code} wall_s={elapsed:.1f}", flush=True)
            if r.status_code != 200:
                print(r.text[:1500], flush=True)
                any_hard_fail = True
                continue
            data = r.json()
            session_id = data.get("session_id") or session_id
            dept = data.get("department")
            agent = data.get("target_agent")
            ans = (data.get("answer") or "").strip()
            elog = data.get("execution_log") or []

            print(f"department={dept} target_agent={agent}", flush=True)
            print(f"lens_request_id={data.get('lens_request_id')}", flush=True)
            print(f"answer_len={len(ans)}", flush=True)

            joined_log = "\n".join(elog)
            print("--- execution_log (tail) ---", flush=True)
            for line in elog[-18:]:
                print(line, flush=True)

            print("--- answer preview ---", flush=True)
            prev = ans[:1200].replace("\n", "\n")
            print(prev + ("…" if len(ans) > 1200 else ""), flush=True)

            if dept != want_dept:
                _fail(f"department want {want_dept!r} got {dept!r}")
                any_hard_fail = True
            else:
                _ok(f"department {dept!r}")

            low = ans.lower()
            log_low = joined_log.lower()
            ta = (agent or "").lower()

            if name.startswith("Events") and "events" not in ta:
                _fail(f"Events — target_agent should reference events, got {agent!r}")
                any_hard_fail = True
            elif name.startswith("Events"):
                _ok(f"Events — target_agent {agent!r}")

            if name.startswith("Chat") and "chat" not in ta:
                _fail(f"Chat — target_agent should reference chat, got {agent!r}")
                any_hard_fail = True
            elif name.startswith("Chat"):
                _ok(f"Chat — target_agent {agent!r}")

            if name.startswith("Engineering") and "eng" not in ta:
                _fail(f"Engineering — target_agent should reference eng_lead/engineering, got {agent!r}")
                any_hard_fail = True
            elif name.startswith("Engineering"):
                _ok(f"Engineering — target_agent {agent!r}")

            if name.startswith("X-Ray") and "xray" not in ta:
                _fail(f"X-Ray — target_agent should reference xray, got {agent!r}")
                any_hard_fail = True
            elif name.startswith("X-Ray"):
                _ok(f"X-Ray — target_agent {agent!r}")

            if "Routed locally" in joined_log:
                _fail("log contains 'Routed locally'")
                any_hard_fail = True
            else:
                _ok("no 'Routed locally' in execution_log")

            if name.startswith("Events"):
                bad = [
                    "don't delete",
                    "dont delete",
                    "gtm.",
                    "star star share",
                    "gjs-",
                ]
                hit = [b for b in bad if b in low]
                if hit:
                    _fail(f"Events answer echo/leak markers: {hit}")
                    any_hard_fail = True
                else:
                    _ok("Events — no obvious HTML/GTM leak substrings")
                lead = ans.lstrip().lower()
                if lead.startswith("session details:"):
                    _fail(
                        "Events — answer must not lead with raw retrieve_event_info dump (summary only)"
                    )
                    any_hard_fail = True
                else:
                    _ok("Events — answer is not raw 'Session Details:' tool prefix")

            if name.startswith("Chat"):
                if "```" in ans and ("terraform" in low or "resource " in low):
                    _fail("Chat answer looks like code fence / infra; expected consultative only")
                    any_hard_fail = True
                else:
                    _ok("Chat — no Terraform-style fence-heavy output heuristic")

            if name.startswith("Engineering"):
                ok_pipe = any(
                    x in joined_log
                    for x in (
                        "Scout",
                        "Coder",
                        "Quality and Security Reviewer",
                        "Sentinel",
                    )
                )
                if not ok_pipe:
                    _fail("Engineering — expected Scout/Coder/Reviewer in logs")
                    any_hard_fail = True
                else:
                    _ok("Engineering — pipeline steps present")
                # One module is a single ```terraform … ``` pair (count 2). Also require Terraform signals
                # so a random ``` pair in prose cannot satisfy the check.
                fence = ans.count("```")
                tf_markers = (
                    "```terraform",
                    "```hcl",
                    "```tf",
                    'resource "google_',
                )
                has_tf = any(m in low or m in ans for m in tf_markers)
                mashup = "# ===" in ans or "=== main.tf" in low or "=== variables.tf" in low
                if mashup:
                    _fail(
                        "Engineering — answer uses # === file === style; prefer separate ``` fences per file"
                    )
                    any_hard_fail = True
                else:
                    _ok("Engineering — no # === / === main.tf mashup heuristic")

                if fence >= 2 and has_tf:
                    _ok(
                        f"Engineering — fenced Terraform/HCL (``` count={fence}, terraform markers OK)"
                    )
                elif fence < 2:
                    _fail(f"Engineering — expected at least one ``` fence pair, got count {fence}")
                    any_hard_fail = True
                else:
                    _fail(
                        "Engineering — expected ```terraform/```hcl or google_* resource block in answer"
                    )
                    any_hard_fail = True

            if name.startswith("X-Ray"):
                if "TOPOLOGY_REPO" in joined_log or "blueprint" in log_low:
                    _ok("X-Ray — topology/blueprint intent in logs")
                else:
                    _fail("X-Ray — missing TOPOLOGY_REPO / blueprint pipeline signals")
                    any_hard_fail = True
                if "architect" not in log_low:
                    _fail(
                        "X-Ray — expected architect in execution_log (topology → architect path)"
                    )
                    any_hard_fail = True
                else:
                    _ok("X-Ray — architect present in logs")
                if "verification needed" in low:
                    _fail("X-Ray — Verdict leak 'Verification Needed'")
                    any_hard_fail = True
                else:
                    _ok("X-Ray — no 'Verification Needed' in answer")

    print("\n" + "=" * 72, flush=True)
    if any_hard_fail:
        print("OVERALL: FAIL (see CHECK FAIL above)", flush=True)
        return 1
    print("OVERALL: PASS (all scenario checks OK)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
