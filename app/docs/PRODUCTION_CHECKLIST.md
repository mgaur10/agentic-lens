# Production Checklist

Use this checklist before and after deploying Agentic Prism to production (Glass UI, Agent Engines).

---

## 1. Environment variables

### Glass UI (Cloud Run ai-prism-agent-glass-ui)

| Variable | Required | Description |
|----------|----------|-------------|
| GCP_PROJECT_ID | Yes | Google Cloud project ID (use **agentic-prismv333** for this repo) |
| GCP_LOCATION | Yes | Region (e.g. us-west1) |
| AGENTIC_LENS_SUPERVISOR_ENGINE | Yes for routing | Full Supervisor engine resource name. Get from deploy output or scripts/get_agent_engine_id.py supervisor. |
| GLASS_UI_LOGS_FIRESTORE_DATABASE | No | Firestore database ID for persisting session logs (e.g. xray-db or (default)). If set, Live System Logs work across instances. |

### Agent Engines (Vertex AI)

- Project and region from deploy environment (versions.env: PROJECT_ID, REGION).
- For X-Ray knowledge base: set XRAY_KB_DATABASE (e.g. xray-db) in agent runtime if using non-default Firestore.

---

## 2. IAM (least privilege)

### Glass UI Cloud Run service account

| Role / permission | Purpose |
|-------------------|--------|
| roles/aiplatform.user | Query Supervisor and department Reasoning Engines |
| roles/datastore.user | Optional: only if GLASS_UI_LOGS_FIRESTORE_DATABASE is set, for session log persistence |

### Agent Engine service accounts

Each agent uses its own identity. They need Vertex AI (Gemini) and, for X-Ray agents, roles/datastore.user for Firestore (iam_knowledge_base, database e.g. xray-db).

### Cloud Build

Account running gcloud builds submit and gcloud run deploy needs: roles/cloudbuild.builds.builder, storage access (build bucket), roles/run.admin, roles/iam.serviceAccountUser.

---

## 3. Firestore / Datastore

- X-Ray IAM knowledge base: Create Firestore database (e.g. xray-db). Collection: iam_knowledge_base.
- Glass UI session logs (optional): If GLASS_UI_LOGS_FIRESTORE_DATABASE is set, collection glass_ui_session_logs is created on first write. Grant Glass UI SA Firestore read/write.

---

## 4. Health checks

- Liveness: GET /healthz returns 200.
- Readiness: GET /healthz?deep=1 checks GCP_PROJECT_ID and Supervisor config; returns 503 if unhealthy.

---

## 5. Secrets and security

- No hardcoded secrets: use env vars or Secret Manager.
- Keep Model Armor / Security Guard enabled in production.
- CMEK: configure per-department keys in versions.env; see agentic-lens/DEPLOY.md.

---

## 6. Remove legacy UIv1 (Streamlit) from Cloud Run

If the old Streamlit UI service **agentic-lens-ui** is still deployed, remove it so only Glass Prism UI is used:

```bash
GCP_PROJECT_ID=your-project REGION=us-west1 ./scripts/delete_uiv1_cloud_run.sh
```

Then deploy or update Glass Prism UI: `./deploy-glass-ui.sh`.

---

## 7. Post-deploy verification

1. Open Glass UI and send a test query.
2. Confirm response is from the intended department (not Mock).
3. Check Live System Logs show Security, Supervisor, Department.
4. Optional: GET /healthz?deep=1 returns 200 with supervisor_configured true.
5. In Cloud Logging, filter by jsonPayload.event for query_start, supervisor_routing_done, department_call_done, query_done.
