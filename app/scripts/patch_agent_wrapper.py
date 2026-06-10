import os
import glob
import re

# Resolve paths relative to this script, not the working directory
# This script lives at: agentic-lens/app/scripts/patch_agent_wrapper.py
# Agents live at:       agentic-lens/app/agentic-lens/agents/*/agent.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AGENTS_DIR = os.path.join(SCRIPT_DIR, "..", "agentic-lens", "agents")

# ──────────────────────────────────────────────────────────────────────────────
# NOTE: VertexGatewayWrapper is NO LONGER USED.
#
# The previous approach wrapped root_agent in a plain Python class to expose
# 'query' and 'stream_query'. This broke AdkApp.stream_query() because
# AdkApp internally calls ctx.agent.run_async(ctx), which only exists on
# LlmAgent subclasses — not on the plain wrapper.
#
# Method registration is handled by patch_cli.py which patches
# _AGENT_ENGINE_CLASS_METHODS in the ADK's cli_deploy.py.
# AdkApp already exposes stream_query(user_id, message) via its internal runner.
#
# This script now REMOVES any previously injected VertexGatewayWrapper blocks
# from agent.py files to clean up any prior builds that injected it.
# ──────────────────────────────────────────────────────────────────────────────

# Pattern to strip the injected VertexGatewayWrapper block (if present)
WRAPPER_PATTERN = re.compile(
    r'\n*# --- Vertex Gateway Wrapper ---.*?'
    r'if .root_agent. in dir\(\).*?root_agent = VertexGatewayWrapper\(root_agent\)\n?',
    re.DOTALL
)

def main():
    pattern = os.path.join(AGENTS_DIR, "*", "agent.py")
    agent_files = glob.glob(pattern)
    print(f"[patch_agent_wrapper] Scanning: {pattern}")
    print(f"[patch_agent_wrapper] Found {len(agent_files)} agent files")

    if not agent_files:
        print("[patch_agent_wrapper] WARNING: No agent files found — check AGENTS_DIR path!")
        print(f"[patch_agent_wrapper] SCRIPT_DIR={SCRIPT_DIR}")
        print(f"[patch_agent_wrapper] AGENTS_DIR resolved to: {os.path.realpath(AGENTS_DIR)}")
        return

    for fpath in agent_files:
        with open(fpath, "r") as f:
            content = f.read()

        if "VertexGatewayWrapper" in content:
            # Strip the old injected wrapper block
            cleaned = WRAPPER_PATTERN.sub("", content)
            with open(fpath, "w") as f:
                f.write(cleaned)
            print(f"[patch_agent_wrapper] ✅ Cleaned VertexGatewayWrapper from: {fpath}")
        else:
            print(f"[patch_agent_wrapper] ⏭  No wrapper found (clean): {fpath}")

if __name__ == "__main__":
    main()
