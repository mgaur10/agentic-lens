# Agentic-Prism - Model Armor content safety gates
# Templates are created via the Python API (create_model_armor_templates.py);
# gcloud model-armor templates create is unreliable with the current schema.
#
# All filters are enabled in both templates (synced with console configuration).
#
# Template 1: security-medium (Medium)
#   - RAI Filters: Hate Speech, Harassment, Sexually Explicit, Dangerous — MEDIUM_AND_ABOVE
#   - PI and Jailbreak: ENABLED (MEDIUM_AND_ABOVE)
#   - Malicious URI: ENABLED
# Template 2: security-high (High+DLP)
#   - RAI Filters: Hate Speech, Harassment, Sexually Explicit, Dangerous — LOW_AND_ABOVE (Strict)
#   - PI and Jailbreak: ENABLED (LOW_AND_ABOVE)
#   - Malicious URI: ENABLED
#   - SDP: Redaction for PII (basic on create; for DLP templates use
#     update_model_armor_templates.py with SdpAdvancedConfig).
# Outputs: medium_template_id, high_template_id

terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.0"
    }
  }
}

variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "region" {
  type        = string
  default     = "us-east5"
  description = "Primary region (agents/deploy); may differ from model_armor_region."
}

variable "model_armor_region" {
  type        = string
  default     = ""
  description = "Region for Model Armor templates (API is not in all regions). If empty, derived from region: us-east5 -> us-east4."
}

variable "python_path" {
  type        = string
  default     = ""
  description = "Optional path to Python with google-cloud-modelarmor (e.g. agentic-lens/.venv/bin/python3). If empty, uses repo agentic-lens/.venv or system python3."
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  template_medium_id = "security-medium"
  template_high_id   = "security-high"
  # Model Armor API is not available in us-east5; use us-east4 when region is us-east5.
  effective_ma_region = var.model_armor_region != "" ? var.model_armor_region : (var.region == "us-east5" ? "us-east4" : var.region)
  # Repo root (where create_model_armor_templates.py lives): policies -> security -> agentic-lens -> repo root
  repo_root = "${path.module}/../../.."
}

# ---------------------------------------------------------------------------
# Create both templates via Python API (security-medium + security-high)
# Uses existing create_model_armor_templates.py from repo root.
# ---------------------------------------------------------------------------
resource "null_resource" "model_armor_templates_python" {
  triggers = {
    region     = local.effective_ma_region
    project_id = var.project_id
  }

  provisioner "local-exec" {
    # Use TF_VAR_python_path if set; else agentic-lens/.venv (relative to repo root); else python3. Requires: pip install google-cloud-modelarmor (or use venv with agentic-lens/requirements.txt).
    command = "cd '${local.repo_root}' && PYTHON=\"${var.python_path}\"; [ -z \"$PYTHON\" ] && PYTHON=\"agentic-lens/.venv/bin/python3\"; [ -x \"$PYTHON\" ] || PYTHON=python3; \"$PYTHON\" create_model_armor_templates.py '${var.project_id}' '${var.model_armor_region != "" ? var.model_armor_region : local.effective_ma_region}'"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "gcloud model-armor templates delete security-medium --location=${self.triggers.region} --project=${self.triggers.project_id} --quiet || true; gcloud model-armor templates delete security-high --location=${self.triggers.region} --project=${self.triggers.project_id} --quiet || true"
  }
}

# ---------------------------------------------------------------------------
# Outputs — template IDs for ADK agents
# ---------------------------------------------------------------------------
output "medium_template_id" {
  description = "Model Armor template ID for medium policy (security-medium)."
  value       = local.template_medium_id
}

output "high_template_id" {
  description = "Model Armor template ID for high policy (security-high)."
  value       = local.template_high_id
}

output "medium_template_name" {
  description = "Full resource name for medium template."
  value       = "projects/${var.project_id}/locations/${local.effective_ma_region}/templates/${local.template_medium_id}"
}

output "high_template_name" {
  description = "Full resource name for high template."
  value       = "projects/${var.project_id}/locations/${local.effective_ma_region}/templates/${local.template_high_id}"
}
