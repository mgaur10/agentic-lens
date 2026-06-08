# Agent Gateway workbook (Phase 3)

> **`agentic-lens` migration:** Phase 3 **skipped** (`SKIP_AGENT_GATEWAY=1` in `config/migration.env`).
> Glass UI uses **direct** Vertex Reasoning Engine API. Re-enable this workbook only if org policy later requires a gateway.

Use when the **new project already has Agent Gateway** configured at org/project level.

## Current application behavior

- Glass UI → **direct** Vertex Reasoning Engine API (`backend/agent_engine_client.py`).
- Model Armor + Security Guard run in Cloud Run **before** Supervisor engine call.
- Agent Gateway is **not** wired in repo code yet.

## Integration models

### Model A — Tool governance (recommended first)

| Traffic | Path |
|---------|------|
| User → UI | Cloud Run → Supervisor engine → department engine |
| Agent → tools | Engine → **Agent Gateway** → GitHub / GCP APIs |

**Tasks:**

- [ ] Record gateway resource name: `________________________________`
- [ ] Region matches `versions.env` REGION
- [ ] Allow GitHub API for `xray_librarian`
- [ ] Allow `secretmanager.googleapis.com`, `cloudasset.googleapis.com`
- [ ] Allow `discoveryengine.googleapis.com` for Events
- [ ] Deny rules tested (intentional block → clear error in UI)

### Model B — Client-to-agent gateway

| Traffic | Path |
|---------|------|
| User → UI | Cloud Run → **Agent Gateway** → Supervisor engine |

**Tasks:**

- [ ] Requires code change + new env vars (future)
- [ ] IAP audience may be gateway URL
- [ ] Defer unless policy requires

## Agent Registry

| Engine | Registered? | Registry ID |
|--------|---------------|-------------|
| supervisor | | |
| chat | | |
| eng_lead | | |
| events | | |
| xray_manager | | |

## Validation

After Phase 5, run an X-Ray repo query and confirm gateway audit log shows tool egress.

## Notes

```
Gateway admin contact:
Policy version / last updated:
Known denied APIs:

```
