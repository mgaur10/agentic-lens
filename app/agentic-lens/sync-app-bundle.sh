#!/usr/bin/env bash
# Populate migration/app/ with a standalone deployable copy of Agentic Prism.
# Run from repo root: ./migration/sync-app-bundle.sh
# Or from migration/: ./sync-app-bundle.sh
set -euo pipefail

MIGRATION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$MIGRATION_DIR/.." && pwd)"
APP_DIR="$MIGRATION_DIR/app"

echo "Source: $REPO_ROOT"
echo "Target: $APP_DIR"

mkdir -p "$APP_DIR"

RSYNC_EXCLUDES=(
  --exclude '.git/'
  --exclude '.venv/'
  --exclude 'agentic-lens/.venv/'
  --exclude 'migration/'
  --exclude '**/.terraform/'
  --exclude '**/terraform.tfstate*'
  --exclude '**/.terraform.lock.hcl'
  --exclude '*.db'
  --exclude '*.db-journal'
  --exclude '.env'
  --exclude 'versions.env'
  --exclude '__pycache__/'
  --exclude '**/__pycache__/'
  --exclude '.cursor/'
  --exclude '**/node_modules/'
  --exclude 'gke-autopilot-private/'
  --exclude 'old_files/'
  --exclude '.agent_engine_config.json'
  --exclude 'schema_full.txt'
  --exclude 'identities_full.txt'
)

# Core deploy tree
rsync -a --delete "${RSYNC_EXCLUDES[@]}" \
  "$REPO_ROOT/agentic-lens/" "$APP_DIR/agentic-lens/"

rsync -a --delete "${RSYNC_EXCLUDES[@]}" \
  "$REPO_ROOT/backend/" "$APP_DIR/backend/"

rsync -a --delete "${RSYNC_EXCLUDES[@]}" \
  "$REPO_ROOT/infra/" "$APP_DIR/infra/"

rsync -a --delete "${RSYNC_EXCLUDES[@]}" \
  "$REPO_ROOT/scripts/" "$APP_DIR/scripts/"

rsync -a --delete "${RSYNC_EXCLUDES[@]}" \
  "$REPO_ROOT/tests/" "$APP_DIR/tests/"

# Root deploy files
for f in \
  deploy.sh deploy-glass-ui.sh deploy_all.sh deploy_model_armor.sh setup_infra.sh \
  glass_ui_api.py requirements.txt requirements-dev.txt pytest.ini env.example \
  cloudbuild_glass_ui.yaml Dockerfile_glass_ui .gcloudignore Makefile \
  create_dlp_templates.py create_model_armor_templates.py; do
  [[ -f "$REPO_ROOT/$f" ]] && cp -f "$REPO_ROOT/$f" "$APP_DIR/$f"
done

# Key docs (reference at destination)
mkdir -p "$APP_DIR/docs"
for f in README_v3.md PRODUCTION_CHECKLIST.md CONVENTIONS.md FEEDBACK_SYSTEM.md DEPLOY_GUIDE_agentic-prismv333.md; do
  [[ -f "$REPO_ROOT/$f" ]] && cp -f "$REPO_ROOT/$f" "$APP_DIR/docs/"
done
for f in agentic-lens/DEPLOY.md agentic-lens/ENABLE_APIS.md agentic-lens/AGENTIC_LENS_COMPLIANCE.md; do
  [[ -f "$REPO_ROOT/$f" ]] && cp -f "$REPO_ROOT/$f" "$APP_DIR/docs/$(basename "$f")"
done
[[ -f "$REPO_ROOT/docs/lens-tracing-verification.md" ]] && \
  cp -f "$REPO_ROOT/docs/lens-tracing-verification.md" "$APP_DIR/docs/" 2>/dev/null || true

# Templates at app root (from migration pack)
cp -f "$MIGRATION_DIR/config/versions.env.template" "$APP_DIR/versions.env.template"
cp -f "$MIGRATION_DIR/config/env.template" "$APP_DIR/env.example.migration"

# Shell scripts must be executable after rsync (mode not always preserved in zip)
find "$APP_DIR/agentic-lens/scripts" -name '*.sh' -type f -exec chmod +x {} + 2>/dev/null || true
find "$APP_DIR/infra" -name '*.sh' -type f -exec chmod +x {} + 2>/dev/null || true

echo ""
echo "Bundle synced to $APP_DIR"
du -sh "$APP_DIR" "$APP_DIR/agentic-lens" 2>/dev/null || true
echo "Next: ./scripts/validate-phase2-agent-sources.sh  (after agent source changes)"
echo "       zip the migration/ folder only (see PACKAGING.md)"
