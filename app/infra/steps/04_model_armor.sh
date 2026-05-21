#!/usr/bin/env bash
# Step 04: Model Armor full deployment.
set -euo pipefail
ROOT_DIR="${ROOT_DIR:?}"
source "$ROOT_DIR/versions.env"
"$ROOT_DIR/deploy_model_armor.sh"
echo "Model Armor step done."
