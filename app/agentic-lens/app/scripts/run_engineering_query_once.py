#!/usr/bin/env python3
"""One-shot Glass UI query for local testing (loads .env from repo root)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from glass_ui_api import QueryRequest, _execute_query_request

PROMPT = (
    "Write the Terraform code to deploy a highly available Cloud Run service connected "
    "to a private Cloud SQL PostgreSQL instance. I need the code properly modularized "
    "into main.tf, variables.tf, and outputs.tf, and it must use production-ready "
    "variable placeholders, not hardcoded strings."
)


def main() -> None:
    req = QueryRequest(
        message=PROMPT,
        armor_enabled=True,
        armor_level="medium",
    )
    print("Calling _execute_query_request (Supervisor + Engineering may take several minutes)...", flush=True)
    out = _execute_query_request(req)
    d = out.model_dump()
    ans = d.get("answer") or ""
    print("department:", d.get("department"), flush=True)
    print("target_agent:", d.get("target_agent"), flush=True)
    print("blocked_by_armor:", d.get("blocked_by_armor"), flush=True)
    print("guard_blocked:", d.get("guard_blocked"), flush=True)
    print("answer_length:", len(ans), flush=True)
    print("--- answer (first 6000 chars) ---", flush=True)
    print(ans[:6000], flush=True)
    if len(ans) > 6000:
        print(f"\n... [truncated, total {len(ans)} chars]", flush=True)
    print("--- execution_log (last 40 lines) ---", flush=True)
    for line in (d.get("execution_log") or [])[-40:]:
        print(line, flush=True)
    out_path = ROOT / "scripts" / "_last_engineering_query_output.json"
    try:
        # Serialize without huge duplication if answer is enormous
        slim = {**d, "answer": ans[:50000] + ("..." if len(ans) > 50000 else "")}
        out_path.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")
        print(f"Wrote partial JSON to {out_path}", flush=True)
    except OSError as e:
        print(f"Could not write {out_path}: {e}", flush=True)


if __name__ == "__main__":
    main()
