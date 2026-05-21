#!/usr/bin/env bash
# Clean local and Terraform state for a fresh install on a new GCP project.
# Removes: .env, *.db, venvs, Terraform state/dirs (db, policies, iam, vpc_sc), agent .agent_engine_config.json.
# Usage: ./scripts/clean_for_fresh_install.sh [--force|-f to skip confirmation]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

FORCE=""
[[ "${1:-}" == "-f" || "${1:-}" == "--force" ]] && FORCE="1"

if [[ -z "$FORCE" ]]; then
  echo "This will remove local .env, venvs, Terraform state, and agent engine configs (ready for a new project)."
  read -r -p "Continue? [y/N] " reply
  if [[ "${reply^^}" != "Y" && "${reply^^}" != "YES" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

REMOVED=()

# .env
[[ -f .env ]] && rm -f .env && REMOVED+=(".env")

# Runtime DBs and dumps (root)
for f in *.db *.db-journal schema_full.txt identities_full.txt; do
  [[ -e "$f" ]] && rm -f "$f" && REMOVED+=("$f")
done

# Venvs
[[ -d .venv ]] && rm -rf .venv && REMOVED+=(".venv")
[[ -d agentic-lens/.venv ]] && rm -rf agentic-lens/.venv && REMOVED+=("agentic-lens/.venv")

# Terraform: db, policies, iam, vpc_sc
for dir in agentic-lens/security/db agentic-lens/security/policies agentic-lens/security/iam agentic-lens/security/vpc_sc; do
  [[ ! -d "$dir" ]] && continue
  [[ -d "$dir/.terraform" ]] && rm -rf "$dir/.terraform" && REMOVED+=("$dir/.terraform")
  [[ -f "$dir/terraform.tfstate" ]] && rm -f "$dir/terraform.tfstate" && REMOVED+=("$dir/terraform.tfstate")
  [[ -f "$dir/terraform.tfstate.backup" ]] && rm -f "$dir/terraform.tfstate.backup" && REMOVED+=("$dir/terraform.tfstate.backup")
  for b in "$dir"/terraform.tfstate.*.backup; do
    [[ -f "$b" ]] && rm -f "$b" && REMOVED+=("$b")
  done
  [[ -f "$dir/.terraform.lock.hcl" ]] && rm -f "$dir/.terraform.lock.hcl" && REMOVED+=("$dir/.terraform.lock.hcl")
done
# IAM: project-specific tfvars
[[ -f agentic-lens/security/iam/terraform.tfvars ]] && rm -f agentic-lens/security/iam/terraform.tfvars && REMOVED+=("agentic-lens/security/iam/terraform.tfvars")

# Agent engine configs (deploy.sh will write fresh)
AGENTS=(supervisor chat eng_lead eng_scout eng_coder eng_quality_and_security_reviewer xray_manager xray_librarian xray_architect xray_specialist xray_auditor events)
for agent in "${AGENTS[@]}"; do
  cfg="agentic-lens/agents/$agent/.agent_engine_config.json"
  [[ -f "$cfg" ]] && rm -f "$cfg" && REMOVED+=("$cfg")
done

echo ""
echo "Cleaned for fresh install."
if [[ ${#REMOVED[@]} -gt 0 ]]; then
  echo "Removed: ${REMOVED[*]}"
else
  echo "Nothing to remove (already clean)."
fi
echo ""
echo "Ready for fresh install. Set PROJECT_ID (and REGION, MODEL_VERSION) in versions.env, then run:"
echo "  ./deploy_all.sh"
echo ""
