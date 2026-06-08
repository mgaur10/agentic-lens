#!/usr/bin/env python3
"""
Merge projects/.../reasoningEngines/<id> into eng_lead and xray_manager Agent Engine env.

Agent-to-agent calls use agent_engines.get(full_resource_name). Listing engines at runtime
often fails under the agent identity, so explicit env vars are required.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _parse_versions_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def _engine_id(root: Path, project: str, region: str, agent_folder: str) -> str:
    script = root / "scripts" / "get_agent_engine_id.py"
    r = subprocess.run(
        [sys.executable, str(script), project, region, agent_folder],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def _merge_json(path: Path, updates: dict[str, str]) -> None:
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    ev = data.setdefault("env_vars", {})
    for key, val in updates.items():
        if val:
            ev[key] = val
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    vers = _parse_versions_env(root / "versions.env")
    project = vers.get("PROJECT_ID") or os.environ.get("PROJECT_ID") or ""
    region = (vers.get("REGION") or os.environ.get("REGION") or "us-west1").strip()
    if not project:
        print("merge_peer_engine_env: PROJECT_ID not set; skipping", file=sys.stderr)
        return 0

    agents = root / "agentic-lens" / "agents"
    xref = {
        "AGENTIC_LENS_ENGINE_XRAY_ARCHITECT": _engine_id(root, project, region, "xray_architect"),
        "AGENTIC_LENS_ENGINE_XRAY_SPECIALIST": _engine_id(root, project, region, "xray_specialist"),
        "AGENTIC_LENS_ENGINE_XRAY_LIBRARIAN": _engine_id(root, project, region, "xray_librarian"),
        "AGENTIC_LENS_ENGINE_XRAY_AUDITOR": _engine_id(root, project, region, "xray_auditor"),
    }
    eng = {
        "AGENTIC_LENS_ENGINE_SCOUT": _engine_id(root, project, region, "eng_scout"),
        "AGENTIC_LENS_ENGINE_CODER": _engine_id(root, project, region, "eng_coder"),
        "AGENTIC_LENS_ENGINE_QUALITY_AND_SECURITY_REVIEWER": _engine_id(
            root, project, region, "eng_quality_and_security_reviewer"
        ),
    }
    chat_val = _engine_id(root, project, region, "chat")

    _merge_json(agents / "xray_manager" / ".agent_engine_config.json", xref)
    _merge_json(agents / "eng_lead" / ".agent_engine_config.json", eng)
    _merge_json(agents / "supervisor" / ".agent_engine_config.json", {
        **xref, 
        **eng, 
        "CHAT_ENGINE_ID": chat_val,
        "GCP_PROJECT_ID": project
    })

    miss = [k for k, v in {**xref, **eng, "CHAT_ENGINE_ID": chat_val}.items() if not v]
    if miss:
        print("merge_peer_engine_env: missing IDs for: " + ", ".join(miss), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
