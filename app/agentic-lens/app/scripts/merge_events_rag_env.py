#!/usr/bin/env python3
"""
Merge Vertex RAG-related variables from repo-root .env into
agentic-lens/agents/events/.agent_engine_config.json env_vars.

Agent Engine containers do not load .env; retrieval must get corpus/project/location
from env_vars on the deployed engine.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Keys to copy from .env into Events Agent Engine (subset avoids leaking secrets).
RAG_ENV_PREFIXES = ("VERTEX_RAG_",)
ALSO_COPY = ("GCP_PROJECT_ID", "GCP_LOCATION")


def parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        out[key] = val
    return out


def pick_rag_env(env: dict[str, str]) -> dict[str, str]:
    picked: dict[str, str] = {}
    for k, v in env.items():
        if not v:
            continue
        if k.startswith(RAG_ENV_PREFIXES) or k in ALSO_COPY:
            picked[k] = v
    return picked


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: merge_events_rag_env.py <path-to-.env> <path-to-events-.agent_engine_config.json>", file=sys.stderr)
        return 2
    env_path = Path(sys.argv[1])
    config_path = Path(sys.argv[2])
    merged = pick_rag_env(parse_dotenv(env_path))
    if not merged:
        print("merge_events_rag_env: no VERTEX_RAG_* (or GCP_*) keys in .env; skipping", file=sys.stderr)
        return 0
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    ev = data.setdefault("env_vars", {})
    if not isinstance(ev, dict):
        ev = {}
        data["env_vars"] = ev
    for k, v in merged.items():
        ev[k] = v
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"merge_events_rag_env: wrote {len(merged)} keys to {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
