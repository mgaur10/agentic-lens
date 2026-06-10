import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: patch_cli.py <path_to_cli_deploy.py>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r") as f:
        text = f.read()

    # ── Patch 1: Replace _AGENT_ENGINE_CLASS_METHODS ────────────────────────
    # Expose only `query` and `stream_query` so Agent Gateway can discover them.
    part1 = text.split("_AGENT_ENGINE_CLASS_METHODS = [")[0]
    part2 = "def _resolve_project(" + text.split("def _resolve_project(")[1]

    new_methods = """_AGENT_ENGINE_CLASS_METHODS = [
    {"name": "query", "description": "Standard Vertex AI query method.", "api_mode": "", "parameters": {"type": "object", "properties": {"message": {"type": "string"}, "session_id": {"type": "string"}}}},
    {"name": "stream_query", "description": "Standard Vertex AI stream_query method.", "api_mode": "stream", "parameters": {"type": "object", "properties": {"message": {"type": "string"}, "session_id": {"type": "string"}}}}
]

"""

    patched_text = part1 + new_methods + part2
    print("✅ Patch 1: _AGENT_ENGINE_CLASS_METHODS replaced (query + stream_query)")

    # ── Patch 2: Fix env_vars OVERWRITE → MERGE ──────────────────────────────
    # Root-cause of custom.enforceReasoningEngineOtelConfig violations:
    # cli_deploy.py unconditionally sets:
    #   agent_config['env_vars'] = env_vars   ← wipes ALL config-file env_vars!
    # leaving only GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY, which drops the
    # two other required OTEL vars (OTEL_SEMCONV_STABILITY_OPT_IN and
    # OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT).
    # Fix: MERGE cli/env-file vars ON TOP of the config-file vars so nothing is lost.
    # ── Patch 2 (robust): Fix env_vars OVERWRITE → MERGE ────────────────────
    # Targets the SINGLE SPECIFIC LINE that overwrites all config env_vars.
    # Using a single-line match is version-agnostic (handles any indentation
    # or surrounding-code changes across google-adk versions).
    # We try both single-quote and double-quote dict key variants.
    patch2_applied = False
    for q in ("'", '"'):
        # The exact overwrite line (any leading indent) — only the assignment,
        # NOT the fallback line `agent_config[x] = agent_config.get(x, env_vars)`
        old_line = f"agent_config[{q}env_vars{q}] = env_vars"
        new_lines = (
            f"_ev_org_merged = {{**(agent_config.get({q}env_vars{q}) or {{}}), **env_vars}}\n"
            f"        agent_config[{q}env_vars{q}] = _ev_org_merged\n"
            f"        print(f'[org-policy-patch] env_vars merged: {{sorted(_ev_org_merged.keys())}}')"
        )
        if old_line in patched_text:
            patched_text = patched_text.replace(old_line, new_lines, 1)
            print(f"✅ Patch 2: env_vars overwrite → merge (key quote={q!r}) — OTEL vars preserved")
            patch2_applied = True
            break

    if not patch2_applied:
        print("⚠️  Patch 2: FAILED — 'agent_config[env_vars] = env_vars' not found in cli_deploy.py")
        print("   Dumping first 3 occurrences of 'env_vars' lines for diagnosis:")
        count = 0
        for i, line in enumerate(patched_text.splitlines()):
            if 'env_vars' in line and 'agent_config' in line:
                print(f"   line {i+1}: {line!r}")
                count += 1
                if count >= 3:
                    break

    with open(path, "w") as f:
        f.write(patched_text)

if __name__ == "__main__":
    main()
