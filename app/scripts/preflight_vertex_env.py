#!/usr/bin/env python3
"""Validate Agent Engine JSON has GCP + Vertex flags after merge_agent_vertex_env / deploy prep."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / "agentic-lens" / "agents"
REQUIRED = ("GOOGLE_GENAI_USE_VERTEXAI", "GCP_PROJECT_ID", "GCP_LOCATION")
# Agents that must exist for a full E2E (optional check)
OPTIONAL_AGENTS = (
    "supervisor",
    "chat",
    "eng_lead",
    "eng_scout",
    "eng_coder",
)
ENG_LEAD_PEERS = (
    "AGENTIC_LENS_ENGINE_SCOUT",
    "AGENTIC_LENS_ENGINE_CODER",
    "AGENTIC_LENS_ENGINE_QUALITY_AND_SECURITY_REVIEWER",
)


def main() -> int:
    errs: list[str] = []
    for name in OPTIONAL_AGENTS:
        cfg = AGENTS_DIR / name / ".agent_engine_config.json"
        if not cfg.is_file():
            errs.append(f"{name}: no .agent_engine_config.json")
            continue
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errs.append(f"{name}: invalid JSON ({e})")
            continue
        ev = data.get("env_vars") or {}
        for k in REQUIRED:
            if k == "GOOGLE_GENAI_USE_VERTEXAI":
                v = (ev.get(k) or "").strip().lower()
                if v not in ("true", "1"):
                    errs.append(f"{name}: missing or false {k!r}")
            else:
                if not (ev.get(k) or "").strip():
                    errs.append(f"{name}: missing {k!r}")
        if name == "eng_lead":
            for pk in ENG_LEAD_PEERS:
                if not (ev.get(pk) or "").strip():
                    errs.append(f"eng_lead: missing {pk} (run ./deploy.sh after merge_peer_engine_env.py)")
    if errs:
        print("preflight_vertex_env: FAILED", file=sys.stderr)
        for e in errs:
            print(f"  {e}", file=sys.stderr)
        print(
            "  Hint: run from repo root: python3 scripts/merge_engineering_vertex_env.py .",
            file=sys.stderr,
        )
        print(
            "        then: python3 scripts/merge_peer_engine_env.py .",
            file=sys.stderr,
        )
        return 1
    print("preflight_vertex_env: OK (supervisor, chat, eng_* have GCP + Vertex; eng_lead has peer IDs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
