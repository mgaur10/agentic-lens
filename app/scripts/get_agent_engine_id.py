#!/usr/bin/env python3
"""
Resolve an Agent Engine resource name by display name (e.g. supervisor -> projects/.../reasoningEngines/ID).
Used by deploy_all.sh and for manual lookup. Exits 0 and prints resource name, or exits 1 with no output.
"""
import os
import sys
import json
import time

DEBUG_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".cursor", "debug-0ff22e.log")

def _log(msg: str, loc: str, hid: str, data: dict) -> None:
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(json.dumps({"sessionId": "0ff22e", "location": loc, "message": msg, "data": data, "timestamp": int(time.time() * 1000), "hypothesisId": hid}) + "\n")
    except Exception:
        pass

# Prefer env; allow args: get_agent_engine_id.py [project_id] [region] agent_name
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    project = os.getenv("PROJECT_ID") or os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    region = (os.getenv("REGION") or os.getenv("GCP_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION") or "us-west1").strip()
    target_name = None
    if len(args) == 1:
        target_name = args[0]
    elif len(args) == 3:
        project, region, target_name = args[0], args[1], args[2]
    elif len(args) == 2:
        project, target_name = args[0], args[1]
    if not target_name:
        print("Usage: get_agent_engine_id.py [PROJECT_ID [REGION]] AGENT_NAME", file=sys.stderr)
        print("  AGENT_NAME e.g. supervisor, chat, eng_lead", file=sys.stderr)
        sys.exit(1)
    if not project:
        print("PROJECT_ID (or GCP_PROJECT_ID) required.", file=sys.stderr)
        sys.exit(1)

    # #region agent log
    _log("get_engine_id_entry", "get_agent_engine_id.py:main", "H1", {"project": project, "region": region, "target": target_name})
    # #endregion
    # Canonical form with hyphens (legacy matching), and with underscores (Vertex AI stores folder name as-is)
    target_clean = target_name.strip().lower().replace("_", "-")
    target_under = target_name.strip().lower().replace("-", "_")  # e.g. xray_specialist
    try:
        import vertexai
        try:
            from vertexai.preview.reasoning_engines import ReasoningEngine
        except ImportError:
            ReasoningEngine = None
        try:
            from vertexai import agent_engines
        except ImportError:
            try:
                from vertexai.preview import agent_engines
            except ImportError:
                agent_engines = None

        vertexai.init(project=project, location=region)
        engines = []
        if ReasoningEngine:
            try:
                # #region agent log
                _log("vertex_list_start", "get_agent_engine_id.py:list", "H1", {"target": target_name})
                # #endregion
                engines = list(ReasoningEngine.list())
                # #region agent log
                _log("vertex_list_done", "get_agent_engine_id.py:list", "H1", {"target": target_name, "n_engines": len(engines)})
                # #endregion
            except Exception as e:
                # #region agent log
                _log("vertex_list_exc", "get_agent_engine_id.py:list", "H1", {"target": target_name, "error": str(e)[:200]})
                # #endregion
                pass
        if not engines and agent_engines:
            try:
                engines = list(agent_engines.list())
            except Exception:
                pass

        # Collect all matching engines.
        # Vertex AI display name = ADK agent folder name (underscores preserved exactly).
        # target_clean has underscores→hyphens; target_under keeps underscores.
        # We match both forms so eng_lead, xray_specialist etc. are found correctly.
        matches = []
        for e in engines:
            gca = getattr(e, "_gca_resource", None)
            display = (
                (gca.display_name if gca and hasattr(gca, "display_name") else None)
                or getattr(e, "display_name", None)
                or ""
            )
            display_raw = (display or "").strip()
            # Normalise display to both hyphen and underscore forms
            display_hyph = display_raw.lower().replace("_", "-")
            display_und  = display_raw.lower().replace("-", "_")
            out = getattr(e, "resource_name", None) or (gca.name if gca else None)
            if not out:
                continue
            # Strip known prefixes for short-form matching
            def _strip_prefix(s: str) -> str:
                for pfx in ("agentic-lens-", "agentic_lens_", "agentic-prism-", "agentic_prism_"):
                    if s.startswith(pfx):
                        return s[len(pfx):]
                return s
            short_hyph = _strip_prefix(display_hyph)
            short_und  = _strip_prefix(display_und)
            matched = (
                display_hyph == target_clean        # hyphen form exact match
                or display_und  == target_under     # underscore form exact match (primary fix)
                or display_hyph.endswith(f"-{target_clean}")
                or display_und.endswith(f"_{target_under}")
                or short_hyph == target_clean
                or short_und  == target_under
            )
            if matched:
                is_adk = "agentic-lens" in display_raw.lower() or "agentic_lens" in display_raw.lower() \
                          or "agentic-prism" in display_raw.lower() or "agentic_prism" in display_raw.lower()
                matches.append((is_adk, out))
        if matches:
            # Prefer ADK-deployed engine (from deploy.sh) over bootstrap placeholder (from step 02)
            matches.sort(key=lambda x: (not x[0], x[1]))
            print(matches[0][1])
            sys.exit(0)
    except Exception as e:
        print(f"Error resolving engine for {target_name}: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(1)


if __name__ == "__main__":
    main()
