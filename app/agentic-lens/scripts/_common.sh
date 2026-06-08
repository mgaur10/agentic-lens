#!/usr/bin/env bash
# Shared helpers for migration phase scripts.
set -euo pipefail

MIGRATION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Standalone bundle: all application code lives in migration/app/
if [[ -z "${REPO_ROOT:-}" ]]; then
  if [[ -f "$MIGRATION_DIR/app/deploy.sh" ]]; then
    # Standalone zip: application code in migration/app/
    REPO_ROOT="$MIGRATION_DIR/app"
  else
    # Fallback: migration/ inside a full repo checkout (no app bundle yet)
    REPO_ROOT="$(cd "$MIGRATION_DIR/.." && pwd)"
  fi
fi
export MIGRATION_DIR REPO_ROOT

MIGRATION_ENV="$MIGRATION_DIR/config/migration.env"
if [[ -f "$MIGRATION_ENV" ]]; then
  # shellcheck source=/dev/null
  source "$MIGRATION_ENV"
fi

VERSIONS_FILE="$REPO_ROOT/versions.env"
ENV_FILE="$REPO_ROOT/.env"
OUTPUT_DIR="$MIGRATION_DIR/output"
mkdir -p "$OUTPUT_DIR"

die() { echo "ERROR: $*" >&2; exit 1; }

require_repo() {
  if [[ ! -f "$REPO_ROOT/deploy.sh" ]]; then
    die "Missing app bundle at $REPO_ROOT/deploy.sh — run migration/sync-app-bundle.sh from full repo, or unzip a complete migration pack"
  fi
  [[ -f "$REPO_ROOT/infra/apply.sh" ]] || die "Missing infra/apply.sh under $REPO_ROOT"
}

require_versions() {
  [[ -f "$VERSIONS_FILE" ]] || die "Missing $VERSIONS_FILE — run: cp config/versions.env.template app/versions.env (from migration/)"
  # shellcheck source=/dev/null
  source "$VERSIONS_FILE"
  [[ -n "${PROJECT_ID:-}" && "$PROJECT_ID" != *"REPLACE_ME"* ]] || die "Set PROJECT_ID in versions.env"
  [[ -n "${REGION:-}" ]] || die "Set REGION in versions.env"
  export PROJECT_ID REGION MODEL_VERSION ORG_ID ADK_VERSION
}

require_gcloud_project() {
  require_versions
  gcloud config set project "$PROJECT_ID" >/dev/null
  echo "Using GCP project: $PROJECT_ID (region $REGION)"
}

gate_confirm() {
  local phase_name="$1"
  if [[ "${MIGRATION_AUTO_YES:-0}" == "1" ]]; then
    return 0
  fi
  echo ""
  echo "=== Gate: $phase_name complete ==="
  read -r -p "Continue to next phase? [y/N] " reply
  [[ "${reply^^}" == "Y" || "${reply^^}" == "YES" ]] || exit 0
}

log_phase() {
  echo ""
  echo "################################################################"
  echo "# $*"
  echo "################################################################"
  echo ""
}

ensure_venvs() {
  if [[ ! -x "$REPO_ROOT/.venv/bin/python3" ]]; then
    log_phase "Creating root .venv"
    python3 -m venv "$REPO_ROOT/.venv"
    "$REPO_ROOT/.venv/bin/pip" install -q -r "$REPO_ROOT/requirements.txt"
  fi
  if [[ ! -x "$REPO_ROOT/agentic-lens/.venv/bin/python3" ]]; then
    log_phase "Creating agentic-lens/.venv"
    python3 -m venv "$REPO_ROOT/agentic-lens/.venv"
    "$REPO_ROOT/agentic-lens/.venv/bin/pip" install -q -r "$REPO_ROOT/agentic-lens/requirements.txt"
  fi
}

copy_templates_if_missing() {
  if [[ ! -f "$VERSIONS_FILE" ]]; then
    cp "$MIGRATION_DIR/config/versions.env.template" "$VERSIONS_FILE"
    echo "Created $VERSIONS_FILE from template — edit before continuing."
  fi
  if [[ ! -f "$ENV_FILE" ]]; then
    cp "$MIGRATION_DIR/config/env.template" "$ENV_FILE"
    echo "Created $ENV_FILE from template."
  fi
  if [[ ! -f "$MIGRATION_ENV" ]]; then
    cp "$MIGRATION_DIR/config/migration.env.example" "$MIGRATION_ENV"
    echo "Created $MIGRATION_ENV from example."
  fi
}
