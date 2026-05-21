# Lens tracing verification (full rollout)

Use after deploying **Glass UI (Cloud Run)**, **Supervisor**, **all department / X‑Ray reasoning engines**, and with **Telemetry API** enabled on the GCP project.

## Correlation overview

| Signal | Role |
|--------|------|
| **`lens.request_id`** | UUID at `POST /api/query`; same value in logs and span attributes when present |
| **W3C (`traceparent` / `tracestate`)** | Injected at Glass ingress into Supervisor/department payloads as HTML comments; stripped before Model Armor / LLM; used to **parent** remote spans under the Cloud Run trace when valid |
| **OTLP** | Agents export to `https://telemetry.googleapis.com/v1/traces` (plus Cloud Trace) so **Agent Engine → Traces** (including Session view) can correlate |
| **Span links** | Backend child spans may **link** to `lens.api.query` when the parent context does not propagate (e.g. worker threads) |

Wire order on department messages: **`LENS_REQUEST_ID` → `LENS_TRACEPARENT` / `LENS_TRACESTATE` → `PRISM_SESSION_ID` → user text** (agents strip in that order).

## 1. APIs and IAM

1. [Telemetry API](https://console.cloud.google.com/apis/library/telemetry.googleapis.com) — enabled.
2. Agent Engine deploy env (via `deploy.sh` / `.agent_engine_config.json`): `GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true` (and optional `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`).

## 2. API response

1. `POST /api/query` with any prompt.
2. JSON includes **`lens_request_id`**; it matches **`lens.request_id`** on **`lens.api.query`**.

## 3. Cloud Trace

1. Trace Explorer → recent traces for Cloud Run service (Glass UI).
2. Root **`lens.api.query`**: `lens.request_id`, `session.id`, `http.route`.
3. Children: **`lens.backend.get_supervisor_routing`**, **`lens.backend.call_agent_engine`**, **`lens.supervisor.*`**, **`lens.department.*`**, **`lens.*.llm`** (department agents), **`lens.engineering.*`** (eng_lead pipeline) — same `lens.request_id` where applicable.
4. **Links**: open spans that use ingress links and confirm a link to **`lens.api.query`**.
5. **W3C**: Vertex spans under a single user request should often share a trace id with Glass when markers were injected (no duplicate roots unless the incoming `traceparent` was invalid).

## 4. Agent Engine console (Traces)

1. Vertex → Agent Engine → instance → **Traces** (Session or Span view).
2. After new traffic, confirm rows appear (OTLP path). If Session view is empty but Cloud Trace is full, check reasoning-engine logs for OTLP export warnings.

## 5. Log correlation

Logs Explorer: `jsonPayload.lens_request_id="<uuid>"` (adjust for your sink). **`query_start`** / **`query_done`** should carry the id via structured logging.

## 6. Security / regression

- No `<!-- LENS_* -->` markers in model-facing text (supervisor strip, department `before_model` strip).
- Model Armor / guard paths still return **`QueryResponse`** with **`lens_request_id`**.
- **Eng_lead** `orchestrate_build` continues to strip trace comments before orchestration (`_extract_lens_trace_marker`).

## 7. Deploy checklist (typical)

- **Glass UI**: `deploy-glass-ui.sh` (backend changes for W3C injection + `call_agent_engine` span).
- **Agents**: `./deploy.sh` for any updated engine (Supervisor bundles peer agents; redeploy **Supervisor** after peer changes).
