# Deploy & test Agentic-Prism

## config_agent_utils ImportError (config-based agents)

If deploy or runtime fails with `ImportError: cannot import name 'config_agent_utils' from 'google.adk.agents'`, the ADK version you have does not export `config_agent_utils` from the top-level `google.adk.agents` package. The patch is applied automatically:

- **Infra:** Step 11 of `./infra/apply.sh` runs the patch if `agentic-lens/.venv` exists.
- **Deploy:** `./deploy.sh` runs the patch at start if venv exists.

To run the patch manually (e.g. after recreating .venv or upgrading google-adk):

```bash
# From repo root, after agentic-lens/.venv exists
agentic-lens/.venv/bin/python scripts/patch_adk_config_agent_utils.py
```

Then run `./deploy.sh` again.

## Clean up duplicate Reasoning Engines (optional)

If you have multiple supervisors (or other agents) from repeated deploys, keep one and delete the rest:

```bash
# From repo root; uses PROJECT_ID and REGION from versions.env
agentic-lens/.venv/bin/python scripts/cleanup_reasoning_engines.py --agent supervisor
# Dry-run first:
agentic-lens/.venv/bin/python scripts/cleanup_reasoning_engines.py --agent supervisor --dry-run
```

This keeps the **newest** engine per `display_name` and deletes older duplicates.

To remove the **old single "engineering" agent** (replaced by eng_lead + eng_scout + eng_coder + eng_quality_and_security_reviewer):

```bash
agentic-lens/.venv/bin/python scripts/cleanup_reasoning_engines.py --agent engineering
```

## Force clean rebuild (after fixing ModuleNotFoundError: vertexai.agent_engines)

If you updated `requirements.txt` and import fallbacks, clear staging and deploy **supervisor first** so the backend gets a fresh build:

```bash
# From repo root
source versions.env
rm -rf agentic-lens/agents/*_tmp*   # clear leftover staging dirs

# Deploy supervisor first (single agent, fresh image)
cd agentic-lens && .venv/bin/adk deploy agent_engine --project="$PROJECT_ID" --region="$REGION" agents/supervisor

# If successful, deploy the rest
cd .. && ./deploy.sh
```

## Deploy all agents to Vertex AI Agent Engine

From repo root:

```bash
./deploy.sh
```

This injects `versions.env` into agent manifests and runs:

```bash
cd agentic-lens && .venv/bin/adk deploy agent_engine --project=$PROJECT_ID --region=$REGION agents/supervisor
```

On success you’ll see: `✅ Created agent engine: projects/.../reasoningEngines/<id>` or `✅ Updated agent engine: ...`.

## If no agents deploy (all fail with code 13 or “failed to start”)

**After first deploy**, if you see service usage or Cloud Trace errors: `./scripts/grant_service_usage_to_engines.sh` (requires `.venv`).

Run the diagnostic script from repo root:

```bash
agentic-lens/.venv/bin/python scripts/diagnose_deploy.py
agentic-lens/.venv/bin/python scripts/diagnose_deploy.py --test-list   # also list existing engines
```

Then:

1. **Set quota project** (often fixes “quota exceeded” / code 13 when using user credentials):
   ```bash
   gcloud auth application-default set-quota-project YOUR_PROJECT_ID
   ```
   Use the same project as in `versions.env` (e.g. set YOUR_PROJECT_ID in the command).

2. **Enable APIs** (if the script reports they’re not enabled):
   ```bash
   gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
   ```

3. **Permissions**: Your deploying user (or service account) needs at least `roles/aiplatform.user` on the project. For Owner/Editor, that’s already included.

4. **Retry**: Wait a few minutes and run `./deploy.sh` again; code 13 can be transient.

5. **Get the exact error from logs** (code 13 hides the real message):  
   From repo root, run:
   ```bash
   ./scripts/fetch_deploy_errors.sh 1
   ```
   (Fetches errors from the last 1 hour; pass `2` for 2 hours, etc.)  
   Then:  
   - **Logs Explorer**: Open [Logs Explorer](https://console.cloud.google.com/logs/query), set **Time range** to “Last 1 hour”, and run:
     ```text
     resource.type=("aiplatform.googleapis.com/ReasoningEngine" OR "audited_resource")
     (severity>=ERROR OR textPayload=~"reasoning" OR jsonPayload.message=~"reasoning" OR protoPayload.methodName=~"Reasoning")
     ```
     Or try: **Resource type** = `Vertex AI Reasoning Engine` (if available) and **Severity** = Error.  
   - **From terminal** (set YOUR_PROJECT_ID or use the project from versions.env):
     ```bash
     gcloud logging read 'resource.type=("aiplatform.googleapis.com/ReasoningEngine" OR "audited_resource") AND (severity>=ERROR OR protoPayload.methodName:"Reasoning")' --project=YOUR_PROJECT_ID --limit=20 --format="table(timestamp,severity,jsonPayload.message,textPayload)" --freshness=1h
     ```
     Or to see raw recent errors:
     ```bash
     gcloud logging read 'severity>=ERROR' --project=YOUR_PROJECT_ID --limit=30 --format=json --freshness=1h | head -200
     ```
     The payload will usually contain the real backend error (e.g. permission, quota, image pull, or region).

## Runtime errors (e.g. in ADK runners.py)

If you see a traceback in **Reasoning Engine stderr** that ends at `async for event in agen:` in `google/adk/runners.py`, the log is often truncated and the real exception is on the next line. To get the full error:

- In **Logs Explorer**, filter by the `reasoning_engine_id` in the log (e.g. `2785142117993807872` for eng_scout), **Severity** = Error, and expand the log entry to see the full `textPayload`.
- Ensure all agents use **`cloudpickle>=2.0.0,<3`** in their `requirements.txt`; then redeploy the affected agent(s) with `./deploy.sh <agent_name>`.

## If the engine fails to start (one agent)

Errors you might see:
- `Reasoning Engine resource [...] failed to start and cannot serve traffic`
- `Failed to create Agent Engine: {'code': 13, 'message': 'Please refer to our documentation...'}` (code 13 = INTERNAL / backend error)

1. **Check logs**  
   In [Logs Explorer](https://console.cloud.google.com/logs):  
   - **Resource type**: `Vertex AI Reasoning Engine`  
   - **Resource container**: your project number (e.g. from `gcloud projects describe $PROJECT_ID --format='value(projectNumber)'`)  
   - **Reasoning Engine ID**: use the engine id from the error if present; otherwise list recent engines and pick the one that just failed:
   ```bash
   # From repo root; lists engines so you can find the latest ID
   agentic-lens/.venv/bin/python -c "
   import vertexai
   from vertexai.preview import reasoning_engines
   vertexai.init(project='YOUR_PROJECT_ID', location='YOUR_REGION')
   for e in reasoning_engines.ReasoningEngine.list(order_by='create_time desc')[:5]:
       print(e.resource_name, getattr(e, 'display_name', ''))
   "
   ```
   Then in Logs Explorer, filter by that ID (or by **Time range** = last 1 hour and **Resource type** = Vertex AI Reasoning Engine) to see the real error.

2. **Common causes**  
   - **google-adk version**: Agent Engine requires **`google-adk>=1.5.0`** for AdkApp deployment. Using `google-adk>=0.5.0` can resolve to 1.1.x in the container and cause `ValueError: Unsupported google-adk version: 1.1.1, please use google-adk>=1.5.0`. Pin `google-adk>=1.5.0` in every agent's `requirements.txt`.
   - **Package versions**: All agent `requirements.txt` must pin `pydantic>=2.6.4`, **`cloudpickle>=2.0.0,<3`** (not 3.x), and `google-cloud-aiplatform[adk,agent_engines]>=1.49.0` per [troubleshooting](https://cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/troubleshooting/deploy). Using `cloudpickle>=3.0.0` can cause runtime errors in the ADK runner. Mismatched cloudpickle between local and remote can also cause "failed to start".  
   - **Quota / backend (code 13)**: Rate limits or transient backend errors. Wait a few minutes and run `./deploy.sh` again.  
   - **VPC-SC**: If using VPC Service Controls, add ingress for the Reasoning Engine Service Agent to `storage.googleapis.com` and `artifactregistry.googleapis.com`.  
   - **Permissions**: Ensure the Vertex AI / Agent Engine service agent and agent identities have required roles (see security/iam).

3. **Re-deploy**  
   After fixing deps or permissions, run `./deploy.sh` again. To update an existing engine, use the same engine id (or set `--agent_engine_id` in the script).

## Tracing and CMEK (optional)

**Tracing:** Agent Engine tracing is enabled by setting environment variables on the Agent Engine Runtime. `./deploy.sh` injects these into each agent’s `.agent_engine_config.json` (in `env_vars`), so every deployed agent emits traces and (optionally) prompt/response content. **Prerequisites:** Enable the [Telemetry (OTLP) API](https://cloud.google.com/observability/docs/telemetry-collection) for trace ingestion and the [Cloud Logging API](https://cloud.google.com/logging/docs) if you use log ingestion. See [Trace an agent](https://docs.cloud.google.com/agent-builder/agent-engine/manage/tracing).

**CMEK (per-department, recommended):** Use one key ring per department in us-west1. Each department uses its own KMS key; deploy assigns the key to each agent by department (supervisor, chat, engineering, xray, events).

1. **Create key rings and keys (initial infra):** Step 05 of `./infra/apply.sh` runs `scripts/setup_cmek_per_department.sh`, which creates in `REGION` (e.g. us-west1): one key ring per department (`prism_supervisor_kr`, `prism_chat_kr`, …), one crypto key per key ring, and grants the **Vertex AI Reasoning Engine** and **Vertex AI** service agents `roles/cloudkms.cryptoKeyEncrypterDecrypter` on each key. To run CMEK setup only: `./scripts/setup_cmek_per_department.sh`.

2. **Configure keys in versions.env:** Add (or uncomment) the five key resource names printed by step 05 or the script, e.g.:
   ```bash
   AGENT_ENGINE_KMS_KEY_SUPERVISOR=projects/.../keyRings/prism_supervisor_kr/cryptoKeys/prism_supervisor_key
   AGENT_ENGINE_KMS_KEY_CHAT=...
   AGENT_ENGINE_KMS_KEY_ENGINEERING=...
   AGENT_ENGINE_KMS_KEY_XRAY=...
   AGENT_ENGINE_KMS_KEY_EVENTS=...
   ```

3. **Deploy:** Run `./deploy.sh`. Each agent’s `.agent_engine_config.json` receives the `encryption_spec` for its department’s key. When any CMEK key var is set, deploy prints a **CMEK key assignment** table (agent → key name). You can also confirm by checking any agent’s `agentic-lens/agents/<agent>/.agent_engine_config.json` for an `encryption_spec.kms_key_name` entry.

See [Deploy – CMEK](https://docs.cloud.google.com/agent-builder/agent-engine/deploy#cmek) and [Managing access – CMEK](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/manage/access#cmek).

**Alternative (single key):** To use one key for all agents, set `AGENT_ENGINE_KMS_KEY_NAME` in `versions.env` to the full key resource name; deploy will use it for every agent instead of the per-department keys.

## Configure the client

Set the deployed supervisor engine name. Use the **region** from `versions.env` (e.g. `us-west1`) and the engine ID from deploy output:

```bash
export GOOGLE_CLOUD_PROJECT=agentic-prismv333
export AGENTIC_LENS_SUPERVISOR_ENGINE=projects/$PROJECT_ID/locations/$REGION/reasoningEngines/<engine_id>
```

Example (replace `$PROJECT_ID`, `$REGION`, and `<engine_id>` with your deploy values):

```bash
export AGENTIC_LENS_SUPERVISOR_ENGINE=projects/$PROJECT_ID/locations/$REGION/reasoningEngines/<engine_id>
```

## Engineering Lead (Squad)

The **eng_lead** agent calls Scout, Coder, and Sentinel engines. After deploying those three, set their resource names so the Lead can invoke them:

```bash
export AGENTIC_LENS_ENGINE_SCOUT=projects/$PROJECT_ID/locations/$REGION/reasoningEngines/<scout_id>
export AGENTIC_LENS_ENGINE_CODER=projects/$PROJECT_ID/locations/$REGION/reasoningEngines/<coder_id>
export AGENTIC_LENS_ENGINE_QUALITY_AND_SECURITY_REVIEWER=projects/$PROJECT_ID/locations/$REGION/reasoningEngines/<sentinel_id>
```

Set these in the **Lead** engine’s environment (e.g. via Agent Engine config or .env in the Lead’s deploy context).

## Run the Glass Prism UI

```bash
# From repo root: install deps then start the API (serves UI + backend)
pip install -r requirements.txt  # if needed
uvicorn glass_ui_api:app --reload --host 0.0.0.0 --port 8000
```

Then open the URL (e.g. http://localhost:8000), and send a message. The app calls the deployed supervisor and shows routing (or BLOCK).
