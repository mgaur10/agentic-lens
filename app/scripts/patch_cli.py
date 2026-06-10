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
    OLD_OVERWRITE = (
        "    if env_vars:\n"
        "      if 'env_vars' in agent_config:\n"
        "        click.echo(\n"
        "            f'Overriding env_vars in agent engine config with {env_vars}'\n"
        "        )\n"
        "      agent_config['env_vars'] = env_vars"
    )
    NEW_MERGE = (
        "    if env_vars:\n"
        "      if 'env_vars' in agent_config and isinstance(agent_config.get('env_vars'), dict):\n"
        "        # [org-policy-patch] MERGE: keep all config-file vars, apply cli/env-file vars on top\n"
        "        _merged = dict(agent_config['env_vars'])\n"
        "        _merged.update(env_vars)\n"
        "        agent_config['env_vars'] = _merged\n"
        "        click.echo(f'[org-policy-patch] Merged env_vars ({len(_merged)} vars): {sorted(_merged.keys())}')\n"
        "      else:\n"
        "        agent_config['env_vars'] = env_vars"
    )
    if OLD_OVERWRITE in patched_text:
        patched_text = patched_text.replace(OLD_OVERWRITE, NEW_MERGE, 1)
        print("✅ Patch 2: env_vars overwrite → merge (OTEL vars preserved for org-policy compliance)")
    else:
        print("⚠️  Patch 2: env_vars overwrite pattern not found — cli_deploy.py may have changed layout")
        print("           Check google-adk version and update patch_cli.py if needed.")

    with open(path, "w") as f:
        f.write(patched_text)

if __name__ == "__main__":
    main()
