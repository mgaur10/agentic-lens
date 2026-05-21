#!/usr/bin/env python3
"""
Inject GCP_PROJECT_ID, GCP_LOCATION, REGION into Agent Engine env_vars for all lens agents
(containers do not load .env). Each agent.py calls _vertex_agent_engine_env_bootstrap() before
google.adk (GOOGLE_CLOUD_* are reserved in deployment_spec; set only at process runtime).

Strips GOOGLE_API_KEY / GEMINI_API_KEY from env_vars so ADK uses Vertex + ADC.

Sets GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES=false so google-genai can
refresh OAuth tokens correctly on Agent Engine (mitigates 401 with agent identity).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Keep in sync with deploy.sh ALL_AGENTS (paths use underscores).
AGENTS = (
    "supervisor",
    "chat",
    "eng_lead",
    "eng_scout",
    "eng_coder",
    "eng_quality_and_security_reviewer",
    "xray_manager",
    "xray_librarian",
    "xray_architect",
    "xray_specialist",
    "xray_auditor",
    "events",
)


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


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    vers = _parse_versions_env(root / "versions.env")
    project = (vers.get("PROJECT_ID") or "").strip()
    region = (vers.get("REGION") or "us-west1").strip()
    if not project:
        print("merge_agent_vertex_env: PROJECT_ID missing in versions.env; skipping", file=sys.stderr)
        return 0

    inject = {
        "GCP_PROJECT_ID": project,
        "GCP_LOCATION": region,
        "REGION": region,
        "GOOGLE_GENAI_USE_VERTEXAI": "true",
        "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "false",
    }

    agents_dir = root / "agentic-lens" / "agents"
    for name in AGENTS:
        cfg_path = agents_dir / name / ".agent_engine_config.json"
        if not cfg_path.is_file():
            continue
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        ev = data.setdefault("env_vars", {})
        if not isinstance(ev, dict):
            ev = {}
            data["env_vars"] = ev
        for k, v in inject.items():
            ev[k] = v
        # Vertex rejects these in deployment_spec.env (reserved; set by the platform).
        for _reserved in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"):
            ev.pop(_reserved, None)
        # API keys force the Gemini Developer path; invalid/stale keys → 401 even when
        # GOOGLE_GENAI_USE_VERTEXAI=true. Engineering peers must use Vertex + agent identity ADC.
        for _api in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_AI_API_KEY"):
            ev.pop(_api, None)
        cfg_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"merge_agent_vertex_env: wrote {len(inject)} keys to {cfg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
