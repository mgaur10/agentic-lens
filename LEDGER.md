# Agentic Prism — Migration deployment ledger

**Target project:** `agentic-lens`  
**Project number:** `479509014388`  
**Region:** `us-west1`  
**ORG_ID:** `873180247571` (confirmed)  
**Pack path:** `migration/`  

---

## Phase 0 — Pre-flight

| Field | Value |
|-------|-------|
| **Status** | **Complete** |
| **Sign-off (user)** | **Approved** |

---

## Phase 1 — Infrastructure

| Field | Value |
|-------|-------|
| **Status** | **Complete** |
| **Sign-off (user)** | **Approved** (2026-05-20) |

### Highlights

- Core infra deployed (IAM, Firestore, telemetry, Artifact Registry, Events KB, RAG, Model Armor).
- `github-pat-token` secret with **placeholder** value (replace before private GitHub use).
- `VERTEX_SEARCH_DATA_STORE_ID=events-web-knowledge` in `app/.env`.
- CMEK skipped; VPC-SC step skipped (org perimeter).

**Logs:** `output/phase1-infra.log`, `output/phase1-github-pat.log`

---

## Phase 2 — Reasoning Engines

| Field | Value |
|-------|-------|
| **Status** | **Complete** — 12/12 Active (API verified 2026-05-20) |
| **Sign-off (user)** | **Approved** (2026-05-20) |

### One-command greenfield (next project or full re-deploy)

```bash
cd migration
gcloud auth application-default set-quota-project agentic-lens   # or your target project
./sync-app-bundle.sh          # after any agent edits in repo root
./scripts/phase2-agents.sh    # step1 → step2 → IAM → refresh eng_lead/xray_manager → env → verify
```

### Manual checklist (same order)

| Step | Command / action |
|------|------------------|
| 1 | Edit `agentic-lens/agents/` in **repo root** (not only `migration/app/`) |
| 2 | `./sync-app-bundle.sh` |
| 3 | `./scripts/validate-phase2-agent-sources.sh` |
| 4 | Delete failed/orphan engines in Console (optional but recommended) |
| 5 | `gcloud auth application-default set-quota-project <project>` |
| 6 | `./scripts/phase2-agents.sh` (includes `grant-reasoning-engine-identity-iam.sh` + orchestrator refresh) |
| 7 | `./scripts/verify-phase2-engines.sh` — 12/12; record sign-off in `LEDGER.md` |

### Deploy roster (all 12 — `us-west1`)

| Agent | Engine ID |
|-------|-----------|
| supervisor | `654578854433652736` |
| chat | `6567805165171113984` |
| eng_lead | `6995647129771311104` |
| events | `4451113340306980864` |
| xray_manager | `4252954956702679040` |
| eng_scout | `5126653284412555264` |
| eng_coder | `8315201820590866432` |
| eng_quality_and_security_reviewer | `2862468571752038400` |
| xray_librarian | `7720726669777960960` |
| xray_architect | `7373949498470432768` |
| xray_specialist | `2267993420939132928` |
| xray_auditor | `668089653315764224` |

Full resource names: `migration/output/engine-ids.env` and `migration/app/.env`.

### Learnings (do not repeat)

| # | Learning | Action |
|---|----------|--------|
| 1 | Failed engines often **never appear in Console**. | Logs Explorer: `resource.labels.reasoning_engine_id=<id>` from deploy output. |
| 2 | **Two-step deploy** required on greenfield (`eng_lead` needs peer IDs). | `phase2-agents.sh` only — not a single `./deploy.sh`. |
| 3 | Batch deploy **exits non-zero** if any agent fails. | Retry one agent: `DEPLOY_PARALLEL=1 ./deploy.sh <name>`. |
| 4 | Wrong ADC quota project → SSL / `403` on project number. | `set-quota-project` before deploy. |
| 5 | **supervisor** bundles all departments — slow (~15+ min). | Deploy last; `ADK_DEPLOY_TIMEOUT=1200`. |
| 6 | **No Agent Gateways in deploy** | Phase 3 skipped (`SKIP_AGENT_GATEWAY=1`); direct API only. |
| 7 | **`cloudpickle==3`** breaks runtime | Pin `>=2.0.0,<3` in every `requirements.txt`. |
| 8 | **`eng_scout` needs `root_agent.yaml`** | Validated by `validate-phase2-agent-sources.sh`. |
| 9 | **`LlmAgent.from_config` removed** — supervisor imports peer `agent.py` at startup. | Use `config_agent_utils.from_config` in YAML-based agents. |
| 10 | Fixes only under `migration/app/` are **lost on sync** | Patch repo → `sync-app-bundle.sh`. |
| 11 | **Terraform `/agents/*` ≠ runtime `/reasoningEngines/*` principals** | Run `grant-reasoning-engine-identity-iam.sh` after deploy; redeploy `eng_lead`/`xray_manager`. |
| 12 | **`403 reasoningEngines.get`** on Engineering peer calls | RE principal needs `roles/aiplatform.user` (not only Terraform agent path). |

### Automation (phase scripts)

| Script | Phase | Purpose |
|--------|-------|---------|
| `validate-phase2-agent-sources.sh` | 2 | Fail fast on scout YAML / `from_config` / cloudpickle |
| `grant-reasoning-engine-identity-iam.sh` | **2, 6** | `roles/aiplatform.user` on each engine RE principal |
| `phase2-agents.sh` | 2 | Deploy 12 engines → IAM → refresh `eng_lead`/`xray_manager` → verify |
| `phase6-production-iam.sh` | 6 | Re-run IAM + orchestrator refresh (+ IAP doc) |
| `verify-phase2-engines.sh` | 2 | 12/12 engines via API |

### Post-Phase-2 IAM (`agentic-lens`)

| Field | Value |
|-------|-------|
| **Applied** | **Yes** (2026-05-21) — `grant-reasoning-engine-identity-iam.sh` |
| **Log** | `output/grant-re-identity-iam.log`, `output/phase6-production-iam.log` |
| **Orchestrator refresh** | `eng_lead`, `xray_manager` redeployed with peer env vars |

### Optional follow-ups (this project)

| Item | Why |
|------|-----|
| **Replace `github-pat-token`** | Placeholder secret — required for private GitHub in X-Ray. |
| **Console cleanup** | Delete old failed engine IDs from earlier retries (quota/clutter). |

### Re-deploy one agent

```bash
cd migration/app && set -a && source versions.env && set +a
export DEPLOY_PARALLEL=1 ADK_DEPLOY_TIMEOUT=1200
agentic-lens/.venv/bin/python scripts/merge_peer_engine_env.py .
SKIP_PREFLIGHT=1 ./deploy.sh <agent_name>
cd .. && ./scripts/write-engine-ids-to-env.sh && ./scripts/verify-phase2-engines.sh
```

### Artifacts

- `output/phase2-deploy.log`
- `output/phase2-retry-scout-supervisor.log`
- `output/phase2-retry-supervisor.log`
- `output/engine-ids.env`

---

## Seamless next time — suggestions

**Already in the pack**

- Repo-wide `config_agent_utils.from_config` (no `LlmAgent.from_config`).
- `sync-app-bundle.sh` → `validate-phase2-agent-sources.sh` → `phase2-agents.sh` → `verify-phase2-engines.sh`.
- Ledger + IMPLEMENTATION §7 troubleshooting for scout/supervisor.

**Recommended habits**

1. **Never edit only `migration/app/`** for agent logic — always sync from repo root.
2. **Run validation before any long deploy** — saves 30+ minutes on a bad bundle.
3. **Keep `DEPLOY_PARALLEL=1`** when debugging a single failing agent.
4. **Archive logs** under `output/` per phase (already named); attach engine ID from log line to Logs Explorer.
5. **Sign off each phase in this ledger** before starting the next (gates scope creep).

**Nice-to-have later (not implemented)**

- CI job: `validate-phase2-agent-sources.sh` on PRs touching `agentic-lens/agents/`.
- `write-engine-ids-to-env.sh` also emit xray sub-agent IDs to a separate `engine-ids-xray.env` (only needed if Glass/tests reference them by name).
- Pre-deploy hook in `deploy.sh` that greps for `LlmAgent.from_config` in the agent folder being uploaded.

---

## Phase 3 — Agent Gateway

| Field | Value |
|-------|-------|
| **Status** | **Skipped** — direct connectivity (no gateway in app path) |
| **Sign-off (user)** | **Approved** (2026-05-20) — defer gateway; same as original Prism deploy |

### Decision

- **Glass UI → Cloud Run → Vertex Reasoning Engines** via `backend/agent_engine_client.py` (no `AGENT_GATEWAY_*` env vars).
- Model Armor / Security Guard remain on Cloud Run before supervisor engine call.
- Org Agent Gateway workbook deferred — set `SKIP_AGENT_GATEWAY=0` in `config/migration.env` only if policy requires it later.

**Control flag:** `SKIP_AGENT_GATEWAY=1` in `migration/config/migration.env`

---

## Phase 4 — Glass UI

| Field | Value |
|-------|-------|
| **Status** | **Complete** — Cloud Run `ai-prism-agent-glass-ui` deployed |
| **Last deploy** | 2026-05-21 |
| **Sign-off (user)** | _pending_ |

**URL:** `output/glass-ui-url.txt` — private invoke (user `roles/run.invoker` granted; IAP SA deferred until Phase 6).

**Run:** `./scripts/phase4-glass-ui.sh` · verify: `./scripts/verify-health.sh` (`/api/healthz?deep=1`).

### Notes

- Fixed `.env` quote on `VERTEX_RAG_DESCRIPTION` (unquoted spaces broke `source .env`).
- `deploy-glass-ui.sh` warns if IAP SA missing instead of failing.
- Health check uses `/api/healthz` (Cloud Run edge quirk on bare `/healthz`).

---

## Phase 5 — Validation

| Status | Not started |

---

## Phase 6 — Production IAM + IAP / HTTPS LB

| Field | Value |
|-------|-------|
| **Status** | **IAM applied** — wired in `phase2-agents.sh` + `phase6-production-iam.sh` |
| **Applied** | **Yes** — 2026-05-21 (`phase6-production-iam.sh`: IAM + `eng_lead`/`xray_manager` ✅) |
| **IAP / LB** | Not started — `artifacts/iap-load-balancer.md` |

### Agent identity IAM (critical)

| Layer | Principal path | When |
|-------|----------------|------|
| Terraform (Phase 1 step 06) | `.../agents/agentic_lens_*` | Project IAM from `security/iam/` |
| **Runtime (Phase 2/6)** | `.../reasoningEngines/<id>` | **This is what peer calls use** |

`deploy.sh` grants session roles to the RE principal, but **orchestrators need `roles/aiplatform.user` on the RE principal** for `agent_engines.get(peer)`. Terraform alone is not enough.

**Symptom fixed:** `Pipeline | Coder | FAILED | code=AUTH_403 | reasoningEngines.get` from eng_lead calling eng_coder.

**Also:** Redeploy `eng_lead` after `merge_peer_engine_env.py` so scout/coder/reviewer IDs are in the running engine (`ENGINE_NOT_CONFIGURED` if eng_lead deployed before scout).
