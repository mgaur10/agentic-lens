import os
import sys
import json
import ast
import subprocess

def check_relative_imports(agents_dir, active_agents):
    """
    Simulates Vertex load restrictions by ensuring agent.py does not contain
    relative imports that will crash when loaded as a top-level module.
    """
    errors = []
    for agent in active_agents:
        agent_py = os.path.join(agents_dir, agent, "agent.py")
        if not os.path.exists(agent_py):
            continue
            
        with open(agent_py, "r") as f:
            content = f.read()
            
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.level is not None and node.level > 0:
                        errors.append(f"{agent}/agent.py: Relative import found: 'from {'.' * node.level}{node.module or ''} import ...'. Vertex AI loads agent.py as a top-level module, so relative imports will cause an ImportError.")
        except SyntaxError:
            errors.append(f"{agent}/agent.py: Syntax error.")

    return errors

def check_mandatory_env_vars(agents_dir, active_agents):
    """
    Validates that the required Org Policy environment variables are present in the
    deployment config for each agent.
    """
    mandatory_vars = [
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY",
        "OTEL_SEMCONV_STABILITY_OPT_IN"
    ]
    errors = []
    
    for agent in active_agents:
        config_path = os.path.join(agents_dir, agent, ".agent_engine_config.json")
        if not os.path.exists(config_path):
            continue
            
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                env_vars = config.get("env_vars", {})
                for var in mandatory_vars:
                    if var not in env_vars:
                        errors.append(f"{agent}: Missing mandatory org-policy env var '{var}' in .agent_engine_config.json")
        except json.JSONDecodeError:
            errors.append(f"{agent}: Invalid JSON in .agent_engine_config.json")
            
    return errors

def check_dependency_conflicts(agents_dir, active_agents):
    """
    Merge all active agent requirements and check if the same package is requested
    multiple times with different version constraints.
    """
    import re
    
    package_versions = {}
    errors = []
    
    # Regex to extract package name (e.g., cloudpickle>=2.0.0 -> cloudpickle)
    pkg_pattern = re.compile(r"^([a-zA-Z0-9_-]+)")
    
    for agent in active_agents:
        req_path = os.path.join(agents_dir, agent, "requirements.txt")
        if os.path.exists(req_path):
            with open(req_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        match = pkg_pattern.match(line)
                        if match:
                            pkg_name = match.group(1).lower()
                            if pkg_name in package_versions and package_versions[pkg_name] != line:
                                errors.append(f"Conflict: '{package_versions[pkg_name]}' vs '{line}' (from {agent})")
                            package_versions[pkg_name] = line
                        
    return errors

def check_glass_ui_security(agents_dir):
    """
    Validates that the Glass UI deployment script does not allow unauthenticated access by default,
    ensuring that IAP is enforced at the Load Balancer level.
    """
    import re
    errors = []
    # AGENTS_DIR is ROOT_DIR/agentic-lens/agents, so ROOT_DIR is two levels up
    root_dir = os.path.dirname(os.path.dirname(agents_dir))
    deploy_sh_path = os.path.join(root_dir, "deploy-glass-ui.sh")
    
    if os.path.exists(deploy_sh_path):
        with open(deploy_sh_path, "r") as f:
            content = f.read()
            # Check for hardcoded 1 or default to 1, ignoring comments
            if re.search(r'^\s*GLASS_UI_ALLOW_UNAUTHENTICATED=[\'"]?1[\'"]?', content, re.MULTILINE) or \
               re.search(r'^\s*GLASS_UI_ALLOW_UNAUTHENTICATED=[\'"]?\$\{GLASS_UI_ALLOW_UNAUTHENTICATED:-1\}[\'"]?', content, re.MULTILINE):
                errors.append("deploy-glass-ui.sh: GLASS_UI_ALLOW_UNAUTHENTICATED is set to allow public access. This violates the Model Armor & IAP Edge Security guardrail.")
    return errors

def main():
    if len(sys.argv) < 3:
        print("Usage: python run_preflight_guardrails.py <agents_dir> <agent1> <agent2> ...")
        sys.exit(1)
        
    agents_dir = sys.argv[1]
    active_agents = sys.argv[2:]
    
    print("🛡️ Running Pre-Flight Guardrails...")
    
    all_errors = []
    
    print("  -> Checking for relative imports in agent.py...")
    all_errors.extend(check_relative_imports(agents_dir, active_agents))
    
    print("  -> Validating Org Policy Environment Variables...")
    all_errors.extend(check_mandatory_env_vars(agents_dir, active_agents))
    
    print("  -> Validating Dependency Compatibility (Dry Run)...")
    all_errors.extend(check_dependency_conflicts(agents_dir, active_agents))
    
    print("  -> Validating IAP/Model Armor Edge Security Guardrail...")
    all_errors.extend(check_glass_ui_security(agents_dir))
    
    if all_errors:
        print("\n❌ PRE-FLIGHT GUARDRAILS FAILED. Deployment aborted to prevent Vertex AI failure.")
        for err in all_errors:
            print(f"  - {err}")
        sys.exit(1)
        
    print("✅ Pre-Flight Guardrails passed. Environment is safe to deploy.")
    sys.exit(0)

if __name__ == "__main__":
    main()
