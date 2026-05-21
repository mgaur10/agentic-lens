#!/usr/bin/env python3
"""
List display names of existing Agent Engines in the project (one per line).
Used by deploy.sh with SKIP_EXISTING=1 to skip agents that already have an engine.
Reads PROJECT_ID and REGION from env (same as get_agent_engine_id.py).
"""
import os
import sys


def main():
    project = os.getenv("PROJECT_ID") or os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    region = (os.getenv("REGION") or os.getenv("GCP_LOCATION") or "us-west1").strip()
    if not project:
        print("PROJECT_ID (or GCP_PROJECT_ID) required.", file=sys.stderr)
        sys.exit(1)
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
                engines = list(ReasoningEngine.list())
            except Exception:
                pass
        if not engines and agent_engines:
            try:
                engines = list(agent_engines.list())
            except Exception:
                pass
        for e in engines:
            gca = getattr(e, "_gca_resource", None)
            display = (
                (gca.display_name if gca and hasattr(gca, "display_name") else None)
                or getattr(e, "display_name", None)
                or ""
            )
            if (display or "").strip():
                print((display or "").strip())
    except Exception as e:
        print(f"Error listing engines: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
