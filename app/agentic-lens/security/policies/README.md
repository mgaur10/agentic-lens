# Model Armor templates (Terraform)

Creates **security-medium** (Medium) and **security-high** (High+DLP) Model Armor templates via the **Python API** (not gcloud). The repo script `create_model_armor_templates.py` at the repo root is invoked by Terraform. All filters are enabled in both templates to match console configuration.

**Template 1: `security-medium` (Medium)**
- RAI Filters: Hate Speech, Harassment, Sexually Explicit, Dangerous — `MEDIUM_AND_ABOVE`.
- PI and Jailbreak: ENABLED (`MEDIUM_AND_ABOVE`).
- Malicious URI: ENABLED.

**Template 2: `security-high` (High+DLP)**
- RAI Filters: Hate Speech, Harassment, Sexually Explicit, Dangerous — `LOW_AND_ABOVE` (Strict).
- PI and Jailbreak: ENABLED (`LOW_AND_ABOVE`).
- Malicious URI: ENABLED.
- SDP: Redaction for PII (basic on create; for DLP inspect/deidentify templates use `update_model_armor_templates.py` with SdpAdvancedConfig).

**Outputs:** `medium_template_id`, `high_template_id` (and full template names).

## Prerequisites

- **Python** with `google-cloud-modelarmor` installed. Either:
  - Use a venv: from repo root, `cd agentic-lens && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` (Terraform will use `agentic-lens/.venv/bin/python3` if present), or
  - System: `pip install google-cloud-modelarmor`, or
  - Set `TF_VAR_python_path=/path/to/your/python` (e.g. your venv’s `python3`) when running Terraform.
- **gcloud** authenticated with a principal that has write access to the project (for create and for destroy).

## Apply

From this directory:

```bash
terraform init
terraform apply -var="project_id=agentic-prismv333" -var="region=us-east5"
```

Optional: pass a Python interpreter that has `google-cloud-modelarmor`:

```bash
terraform apply -var="project_id=agentic-prismv333" -var="region=us-east5" -var="python_path=/path/to/agentic-lens/.venv/bin/python3"
```

## Destroy

Templates are deleted via gcloud in the destroy provisioner. Run:

```bash
terraform destroy -var="project_id=agentic-prismv333" -var="region=us-east5"
```
