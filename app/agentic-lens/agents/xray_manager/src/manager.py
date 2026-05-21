"""
X-Ray Manager — Advisory IAM analysis (single-shot, no code validation).

Single-shot pipeline: user query + optional repo context are passed to the X-Ray Specialist LLM,
which returns a Markdown security brief. No Terraform generation, no Auditor / Quality and Security Reviewer loop.

- "Analyze Repo" (github.com / "analyze repo"): Fetch repo via Librarian, then one LLM call.
- Other IAM questions: One LLM call with user query as context.

Safety: Only the Manager has roles/aiplatform.user within X-Ray; it invokes Librarian and
Specialist. See security/iam/agent_permissions.tf.
"""
import logging
import json
import os
import re
import threading
import time

from google.adk.tools.tool_context import ToolContext

logger = logging.getLogger(__name__)


def _init_vertexai_peer(project: str, location: str) -> None:
    try:
        from vertex_init import init_vertexai

        init_vertexai(project, location)
    except ImportError:
        import vertexai

        vertexai.init(project=project, location=location)

_USER_ID = "xray_manager"
# Vertex session IDs are scoped to one ReasoningEngine resource. Passing xray_manager's or Glass's
# session into librarian / auditor / specialist stream_query yields empty streams (no clean error).
# Same policy as eng_lead _orchestrate_build_impl (sub_engine_session_id=None for Scout/Coder).
_PEER_STREAM_SESSION_ID: str | None = None
_PRISM_SESSION_MARKER_RE = re.compile(r"^\s*<!--\s*PRISM_SESSION_ID:([^>]+?)\s*-->\s*\n?", re.IGNORECASE)
_PRISM_EXEC_LOG_START = "<!-- PRISM_EXECUTION_LOG -->"
_PRISM_EXEC_LOG_END = "<!-- /PRISM_EXECUTION_LOG -->"


def _librarian_iam_fetch_prompt(repo_ref: str) -> str:
    """
    Shared Librarian instructions for repo IAM/deploy evidence (used by analyze-repo and orchestrate_xray).
    Covers Terraform, containers, CI/CD, app manifests, and Python/Vertex deploy scripts with strict caps.
    """
    r = (repo_ref or "").strip()
    return (
        "Fetch this repo and return ONLY minimal context needed for an IAM audit of DEPLOY.\n"
        "CRITICAL (hard bans):\n"
        "- Do NOT fetch or output `README.md` (or any file named `readme*`).\n"
        "- Do NOT fetch or output `LICENSE` (or any file named `license*`).\n"
        "- Do NOT fetch or output images or binary-like assets: extensions like `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg`, `.webp`, `.ico`, `.pdf`.\n"
        "- Do NOT fetch or output licenses, diagrams, non-deploy documentation, walkthrough/tutorial content, or any other non-infrastructure docs.\n"
        "- Do NOT return large file contents.\n"
        "- Focus only on infrastructure and deployment inputs.\n\n"
        "Steps:\n"
        "1) Call get_repo_contents(repo) to get a file list.\n"
        "2) Then read ONLY files matching the categories below (use `read_file_content` per path). "
        "**Hard cap: at most 10 distinct files total** across all categories. "
        "For each file, return at most **80 lines** of excerpt (first 80 lines only if longer).\n"
        "   - **Terraform:** any `*.tf` (up to **3** files; prefer `main.tf`, `provider.tf`, `variables.tf`, `outputs.tf`, `versions.tf`).\n"
        "   - **Docker / containers:** `Dockerfile`, `docker-compose.yml`, `docker-compose.yaml` (up to **2** files from this category).\n"
        "   - **CI/CD pipelines:** `cloudbuild.yaml`, `cloudbuild.yml`, `.gitlab-ci.yml`, `skaffold.yaml`, and up to **2** workflow files under `.github/workflows/` (names ending in `.yml` or `.yaml`; prefer deploy/build/test workflows). "
        "Up to **4** files total from this category, still counting toward the 10-file cap.\n"
        "   - **App / dependency manifests (deploy hints):** repo-root `app.yaml` (e.g. App Engine), `requirements.txt`, `package.json` (up to **3** files from this category if present).\n"
        "   - **Python / Vertex / Agent Engine:** always read `deploy.py` if it appears in the file list; plus at most **one** other `*.py` that imports or references `vertexai`, `google.cloud`, `agent_engines`, or `aiplatform`.\n"
        "   If selecting all matches would exceed **10** files, **omit lowest-priority** picks first (e.g. drop extra workflow files, then optional `package.json`, then secondary Python) while keeping Terraform and `deploy.py` when present.\n"
        "3) In the excerpts, prioritize lines that show **Google Cloud** usage: `vertexai`, `agent_engines`, `aiplatform`, `google_*` Terraform resources, `cloudbuild`, `secretmanager`, GCS staging buckets, `artifactregistry`, `run`, App Engine, VPC/network, container registries.\n"
        "   - Do not assume AWS. Capture Dockerfile/compose and CI steps that reference `gcloud`, Artifact Registry, or Cloud Run.\n\n"
        f"Repo: {r}"
    )


def _filter_librarian_evidence(raw_code: str) -> str:
    """
    Best-effort evidence sanitization to enforce Librarian bans in practice.
    This is intentionally conservative: it removes common disallowed filename tokens
    (README.md / LICENSE / images / other *.md) before evidence inference.
    """
    if not raw_code:
        return raw_code

    s = raw_code

    # Remove file-tree/list tokens that reference banned docs/assets.
    # Librarian outputs often look like python list literals of strings.
    s = re.sub(r"(?i)'readme[^']*\.md'\s*,?\s*", "", s)
    s = re.sub(r"(?i)'license[^']*'\s*,?\s*", "", s)
    s = re.sub(
        r"(?i)'[^']*\.(png|jpe?g|gif|svg|webp|ico|pdf)[^']*'\s*,?\s*",
        "",
        s,
    )
    s = re.sub(r"(?i)'[^']*\.md'\s*,?\s*", "", s)

    # Remove any remaining plain tokens that appear outside quotes.
    s = re.sub(r"(?i)\bREADME\.md\b", "", s)
    s = re.sub(r"(?i)\bLICENSE\b", "", s)
    s = re.sub(
        r"(?i)\.(png|jpe?g|gif|svg|webp|ico|pdf)\b",
        "",
        s,
    )

    return s.strip()


def _get_engine_by_display_name(target_name: str) -> str:
    """
    Resolve an Agent Engine resource name by display_name.
    Falls back to empty string if not found.
    """
    if not target_name:
        return ""
    try:
        import vertexai
        try:
            from vertexai import agent_engines
        except ImportError:
            from vertexai.preview import agent_engines

        project = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
        location = (
            os.getenv("GCP_LOCATION")
            or os.getenv("GOOGLE_CLOUD_LOCATION")
            or os.getenv("REGION")
            or "us-west1"
        ).strip()
        if not project:
            return ""

        _init_vertexai_peer(project, location)
        engines = list(agent_engines.list())
        target_clean = target_name.strip().lower().replace("_", "-")

        for e in engines:
            gca = getattr(e, "_gca_resource", None)
            display = (
                (gca.display_name if gca and hasattr(gca, "display_name") else None)
                or getattr(e, "display_name", None)
                or ""
            )
            display_lower = (display or "").strip().lower().replace("_", "-")
            if display_lower == target_clean or display_lower.endswith(f"-{target_clean}"):
                return getattr(e, "resource_name", None) or (gca.name if gca else "") or ""
        return ""
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Could not resolve engine by display name %s: %s", target_name, e)
        return ""


def _merge_stream_text_chunks(chunks: list[str]) -> str:
    """Join stream fragments: token deltas are usually short single-line pieces; full turns use newlines."""
    c: list[str] = []
    for t in chunks:
        if t is None:
            continue
        s = str(t)
        if not s.strip():
            continue
        c.append(s)
    if not c:
        return ""
    if all(len(x) < 200 and "\n" not in x for x in c):
        return "".join(c).strip()
    # Dedupe consecutive duplicates (some SDKs replay the full prefix each chunk).
    deduped: list[str] = []
    for x in c:
        if deduped and x == deduped[-1]:
            continue
        deduped.append(x)
    return "\n".join(deduped).strip()


_SKIP_DEEP_KEYS = frozenset(
    k.lower()
    for k in (
        "thought",
        "thoughtSignature",
        "thought_signature",
        "finishReason",
        "finish_reason",
        "index",
    )
)


def _deep_collect_strings(obj: object, bucket: list[str], *, depth: int = 0) -> None:
    """Last-resort walk for unknown Vertex/ADK dict shapes (keeps longer prose-like strings)."""
    if depth > 12 or obj is None:
        return
    if isinstance(obj, str):
        s = obj.strip()
        if len(s) >= 24:
            bucket.append(s)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in _SKIP_DEEP_KEYS:
                continue
            _deep_collect_strings(v, bucket, depth=depth + 1)
        return
    if isinstance(obj, list):
        for it in obj:
            _deep_collect_strings(it, bucket, depth=depth + 1)


def _collect_from_event(ev: object, out: list[str]) -> None:
    """Collect model/tool text from a Vertex/ADK stream event (dict, list, or SDK object).

    Matches ``backend.agent_engine_client._collect_text`` ordering: structured
    ``content.parts`` / ``function_response`` before top-level ``message``, and
    collects **all** parts in an event (no early return after the first fragment).
    """
    if ev is None:
        return
    if isinstance(ev, str):
        if ev.strip():
            out.append(ev.strip())
        return
    if isinstance(ev, list):
        for item in ev:
            _collect_from_event(item, out)
        return
    if isinstance(ev, dict):
        _before = len(out)
        content = (
            ev.get("content")
            or ev.get("event")
            or ev.get("response")
            or ev.get("candidates")
            or ev.get("chunk")
            or ev.get("data")
        )
        if content is None:
            content = ev
        if isinstance(content, dict):
            inner = content.get("content")
            if isinstance(inner, dict):
                content = inner
            parts = (
                content.get("parts")
                or content.get("Parts")
                or content.get("candidates")
                or [content]
            )
            if not isinstance(parts, list):
                parts = [parts]
            for p in parts:
                if isinstance(p, dict):
                    txt = p.get("text") or p.get("output")
                    if txt:
                        out.append(str(txt).strip())
                    fr = p.get("function_response") or p.get("functionResponse") or {}
                    if isinstance(fr, dict):
                        resp = fr.get("response")
                        if isinstance(resp, dict) and resp.get("result") is not None:
                            out.append(str(resp["result"]).strip())
                        elif isinstance(resp, str) and resp.strip():
                            out.append(resp.strip())
                    nested = p.get("content")
                    if nested is not None:
                        _collect_from_event(nested, out)
                else:
                    _collect_from_event(p, out)
            if len(out) > _before:
                return
        elif isinstance(content, list):
            for item in content:
                _collect_from_event(item, out)
            if len(out) > _before:
                return
            return
        for key in ("text", "summary", "output", "message", "result"):
            val = ev.get(key)
            if isinstance(val, str) and val.strip():
                out.append(val.strip())
                return
        msg = ev.get("message")
        if isinstance(msg, dict):
            _collect_from_event(msg.get("content") or msg.get("parts") or msg, out)
        elif isinstance(msg, str) and msg.strip():
            out.append(msg.strip())
        for m in ev.get("messages") or []:
            if isinstance(m, dict):
                _collect_from_event(m.get("content") or m.get("parts") or m, out)
            elif isinstance(m, str) and m.strip():
                out.append(m.strip())
        for sub in ev.get("events") or []:
            _collect_from_event(sub, out)
        return
    for attr in ("text", "content", "output", "result", "message", "summary"):
        if hasattr(ev, attr):
            val = getattr(ev, attr, None)
            if isinstance(val, str) and val.strip():
                out.append(val.strip())
                return
            if val is not None and not isinstance(val, str):
                _collect_from_event(val, out)
                if out:
                    return
    if hasattr(ev, "parts"):
        _collect_from_event(getattr(ev, "parts", None), out)
    if hasattr(ev, "candidates"):
        _collect_from_event(getattr(ev, "candidates", None), out)


def _extract_prism_session_marker(message: str) -> tuple[str | None, str]:
    """Extract PRISM session marker and return (session_id, cleaned_message)."""
    raw = message or ""
    m = _PRISM_SESSION_MARKER_RE.match(raw)
    if not m:
        return (None, raw)
    sid = (m.group(1) or "").strip()
    cleaned = raw[m.end():]
    return ((sid or None), cleaned)


def _peer_engine_timeout_s() -> int:
    """
    Max seconds to wait for a single peer Reasoning Engine stream (Librarian, Auditor, Specialist).

    Without this, hung streams block forever inside xray_manager while Glass/UI waits on the department hop.
    Default 600s fits two hops (Librarian + Auditor) under a typical 1200s department timeout.
    """
    raw = (os.getenv("XRAY_PEER_ENGINE_TIMEOUT_S") or "").strip()
    if raw.isdigit():
        return max(60, min(int(raw), 3600))
    return 600


def _looks_like_peer_error_payload(s: str) -> bool:
    """True when pipeline output is an error string from _call_engine or SDK (not audit Markdown)."""
    t = (s or "").strip()
    return bool(t.startswith("Error:") or t.startswith("[Error"))


def _call_engine_unbounded(engine_name: str, message: str, session_id: str | None = None) -> str:
    """Call an Agent Engine with message; return combined response text. Extracts text and function_response.response.result from stream."""
    # --- Agent-to-agent (A2A-style) call: we use Vertex Agent Engine SDK (agent_engines.get + stream_query), not the HTTP A2A protocol. ---
    if not engine_name or not engine_name.strip():
        return ""
    try:
        import vertexai
        try:
            from vertexai import agent_engines
        except ImportError:
            from vertexai.preview import agent_engines

        project = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
        location = (
            os.getenv("GCP_LOCATION")
            or os.getenv("GOOGLE_CLOUD_LOCATION")
            or os.getenv("REGION")
            or "us-west1"
        ).strip()
        if not project:
            logger.warning("GCP_PROJECT_ID and GOOGLE_CLOUD_PROJECT are unset")
            return ""
        _init_vertexai_peer(project, location)
        engine = agent_engines.get(engine_name)
        kwargs = {"message": message, "user_id": _USER_ID}
        if session_id:
            kwargs["session_id"] = session_id
        try:
            stream = engine.stream_query(**kwargs)
        except Exception as e_stream:
            # Session IDs are engine-scoped in Agent Engine. If a cross-engine session
            # is not found, retry without session_id to keep orchestration running.
            if session_id and "Session not found" in str(e_stream):
                logger.warning(
                    "Session %s not found for engine %s; retrying without session_id",
                    session_id,
                    engine_name,
                )
                kwargs.pop("session_id", None)
                stream = engine.stream_query(**kwargs)
            else:
                raise
        def _materialize_from_events(ev_list: list[object]) -> str:
            texts_local: list[str] = []
            for ev in ev_list:
                _collect_from_event(ev, texts_local)
            merged_local = _merge_stream_text_chunks(texts_local)
            if merged_local:
                return merged_local
            deep_local: list[str] = []
            for ev in ev_list:
                _deep_collect_strings(ev, deep_local)
            if deep_local:
                deep_local.sort(key=len, reverse=True)
                return deep_local[0].strip()
            return ""

        events = list(stream)
        body = _materialize_from_events(events)
        if body:
            return body
        if session_id:
            kwargs.pop("session_id", None)
            try:
                stream_ns = engine.stream_query(**kwargs)
                body_ns = _materialize_from_events(list(stream_ns))
                if body_ns:
                    logger.info(
                        "Peer engine %s returned text after retry without foreign session_id",
                        (engine_name or "")[-24:],
                    )
                    return body_ns
            except Exception as e_ns:
                logger.debug("stream_query without session_id retry: %s", e_ns)
        try:
            # Some Vertex SDKs expose only `stream_query` on AgentEngine and not `.query()`.
            # In that case, fall back to ReasoningEngine.query() with common parameter names.
            response = None
            if hasattr(engine, "query"):
                response = engine.query(**kwargs)
            else:
                from vertexai.preview.reasoning_engines import ReasoningEngine as RE

                re_engine = RE(engine_name)
                for qkwargs in (
                    {"user_query": message},
                    {"input": message},
                    {"message": message},
                ):
                    try:
                        response = re_engine.query(**qkwargs)
                        break
                    except TypeError:
                        continue

            if response is not None:
                texts_fb: list[str] = []
                _collect_from_event(response, texts_fb)
                if texts_fb:
                    return _merge_stream_text_chunks(texts_fb)
                if hasattr(response, "text") and response.text:
                    return str(response.text).strip()
                try:
                    raw = str(response).strip() if response is not None else ""
                    if raw and raw not in ("{}", "{ }"):
                        return raw
                except Exception:
                    pass
        except Exception as e_fallback:
            logger.warning(
                "Engine stream yielded no text; non-streaming fallback failed: %s",
                e_fallback,
            )
        try:
            time.sleep(0.35)
            ev2_list: list[object] = []
            stream2 = engine.stream_query(**kwargs)
            for ev2 in stream2:
                ev2_list.append(ev2)
            texts_retry: list[str] = []
            for ev2 in ev2_list:
                _collect_from_event(ev2, texts_retry)
            if texts_retry:
                m2 = _merge_stream_text_chunks(texts_retry)
                if m2:
                    return m2
            deep2: list[str] = []
            for ev2 in ev2_list:
                _deep_collect_strings(ev2, deep2)
            if deep2:
                deep2.sort(key=len, reverse=True)
                return deep2[0].strip()
        except Exception as e_retry:
            logger.debug("Engine stream retry failed: %s", e_retry)
        return ""
    except Exception as e:
        logger.exception("Engine call failed: %s", e)
        return f"[Error calling engine: {e}]"


def _call_engine(engine_name: str, message: str, session_id: str | None = None) -> str:
    """
    Same as _call_engine_unbounded but bounded by XRAY_PEER_ENGINE_TIMEOUT_S so a stuck peer
    cannot block the repo IAM pipeline indefinitely.
    """
    if not engine_name or not engine_name.strip():
        return ""
    timeout_s = _peer_engine_timeout_s()
    out: list[str] = []
    err: list[BaseException] = []

    def _worker() -> None:
        try:
            out.append(_call_engine_unbounded(engine_name, message, session_id=session_id))
        except BaseException as e:  # noqa: BLE001 — must surface worker failures
            err.append(e)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        eng = (engine_name or "")[-48:]
        logger.error("Peer engine %s timed out after %ss (stream did not finish)", eng, timeout_s)
        return (
            f"Error: Peer engine timed out after {timeout_s}s ({eng}). "
            "The Librarian or Auditor stream did not complete — check Vertex Agent Engine logs, GitHub API rate limits, "
            "and IAP/load-balancer timeouts. Increase XRAY_PEER_ENGINE_TIMEOUT_S if audits need more time per hop."
        )
    if err:
        e = err[0]
        logger.exception("Peer engine worker failed: %s", e)
        return f"[Error calling engine: {e}]"
    return (out[0] if out else "") or ""


def _gemini_iam_advisory_fallback(user_query: str) -> str:
    """
    In-process Gemini call when peer Reasoning Engines stream back no text.
    Uses the same Vertex identity as xray_manager (no second hop to Agent Engine).
    """
    q = (user_query or "").strip()
    if not q:
        return ""
    try:
        from vertexai.generative_models import GenerativeModel

        project = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
        location = (
            os.getenv("GCP_LOCATION")
            or os.getenv("GOOGLE_CLOUD_LOCATION")
            or os.getenv("REGION")
            or "us-west1"
        ).strip()
        if not project:
            return ""
        _init_vertexai_peer(project, location)
        model = GenerativeModel("gemini-2.5-flash")
        prompt = (
            "You are a Google Cloud IAM expert. Answer in concise Markdown. "
            "Use exact role IDs (e.g. roles/run.invoker) and permission names (e.g. run.routes.invoke) "
            "when applicable. Lead with the minimum required permission, then briefly note scope "
            "(which resource to bind on).\n\n"
            f"Question:\n{q}"
        )
        resp = model.generate_content(
            prompt,
            generation_config={"temperature": 0.2, "max_output_tokens": 2048},
        )
        text = (getattr(resp, "text", None) or "").strip()
        if text:
            return text
    except Exception as e:
        logger.warning("Gemini IAM advisory fallback failed: %s", e)
    return ""


def _call_librarian(query: str, session_id: str | None = None) -> str:
    """Call xray-librarian (Fetch). Librarian uses get_repo_contents then read_file_content."""
    name = (os.getenv("AGENTIC_LENS_ENGINE_XRAY_LIBRARIAN") or "").strip()
    if not name:
        name = _get_engine_by_display_name("xray_librarian")
        if not name:
            return "[Librarian engine not configured. Set AGENTIC_LENS_ENGINE_XRAY_LIBRARIAN or deploy an engine named xray_librarian.]"
    return _call_engine(name, query, session_id=session_id)


def _call_specialist(payload: str, session_id: str | None = None) -> str:
    """Call xray-specialist. Used for advisory Markdown analysis (single-shot)."""
    name = (os.getenv("AGENTIC_LENS_ENGINE_XRAY_SPECIALIST") or "").strip()
    if not name:
        name = _get_engine_by_display_name("xray_specialist")
        if not name:
            return "[Specialist engine not configured. Set AGENTIC_LENS_ENGINE_XRAY_SPECIALIST or deploy an engine named xray_specialist.]"
    return _call_engine(name, payload, session_id=session_id)


def _call_auditor(payload: str, session_id: str | None = None) -> str:
    """Call xray-auditor. Used for repo IAM audits (roles + permissions)."""
    name = (os.getenv("AGENTIC_LENS_ENGINE_XRAY_AUDITOR") or "").strip()
    if not name:
        name = _get_engine_by_display_name("xray_auditor")
        if not name:
            return "[Auditor engine not configured. Set AGENTIC_LENS_ENGINE_XRAY_AUDITOR or deploy an engine named xray_auditor.]"
    return _call_engine(name, payload, session_id=session_id)


def _sanitize_auditor_output(text: str, evidence_text: str) -> str:
    """
    Produce a compact, IAM-only, least-privilege summary for the UI.

    This function is intentionally defensive:
    - It must never pass through large README/diagram prose from the Auditor.
    - It must not include invented services/resources. We do that by:
      - extracting only permission/role tokens,
      - and then validating them against "evidence_text" (what Librarian fetched).
    """
    if not text and not evidence_text:
        return "X-Ray could not analyze this repository. No IAM evidence was produced."

    # Auditor EMPTY CONTEXT RULE: pass through as-is so validator/sanitizer never rewrites
    # compliant N/A outputs into grading-rubric text.
    if text and (
        "No supported infrastructure code found" in text
        or (
            "N/A" in text
            and (
                "Cannot determine roles without infrastructure code" in text
                or "Cannot determine permissions without infrastructure code" in text
            )
        )
    ):
        return text.strip()
    # Backward-compatible empty-context phrasing.
    if text and (
        "N/A - Cannot determine roles without infrastructure code" in text
        and "N/A - Cannot determine permissions without infrastructure code" in text
    ):
        return text.strip()

    evidence_lower = (evidence_text or "").lower()

    # Evidence-driven service allowance (prevents "redis/sql" style hallucinations).
    # We infer allowed services from evidence_text (what the Librarian fetched).
    allowed_services: set[str] = set()
    ev = evidence_lower

    def _any(subs: tuple[str, ...]) -> bool:
        return any(s in ev for s in subs)

    if _any(("vertexai", "agent_engines", "reasoningengines", "reasoningengines/", "aiplatform")):
        allowed_services.add("aiplatform")
    # Storage: avoid matching generic words like "bucket" in unrelated prose — require GCS/Terraform signals.
    if _any(
        (
            "staging_bucket",
            "gs://",
            "gcs://",
            "gcs:",
            "google_storage_bucket",
            "google_storage_bucket_",
            "storage_bucket",
            "storage.googleapis.com",
            "cloud storage",
            'backend "gcs"',
            "backend \"gcs\"",
            "backend 'gcs'",
        )
    ):
        allowed_services.add("storage")
    if _any(("discoveryengine", "agentspace", "authorization", "oauth", "discovery-engine")):
        allowed_services.add("discoveryengine")
    if _any(("telemetry", "trace", "cloudtrace", "cloud trace", "logging.", "monitoring.", "stackdriver")):
        allowed_services.add("telemetry")
    if _any(("iam.", "iam:", "iam/", "google_iam", "google_service_account", "service account", "serviceaccount", "iam_binding")):
        allowed_services.add("iam")

    # DevSecOps / Terraform common services
    if _any(("cloudbuild", "cloud_build", "cloud-build", "build.googleapis.com", "google_cloudbuild", "cloud build")):
        allowed_services.add("cloudbuild")
    if _any(("artifactregistry", "artifact_registry", "artifact registry", "google_artifact_registry")):
        allowed_services.add("artifactregistry")
    if _any(("secretmanager", "secret_manager", "secret manager", "google_secret_manager", "kms:", "secretmanager.")):
        allowed_services.add("secretmanager")
    if _any(("cloudkms", "cloud_kms", "kms", "crypto_key", "google_kms", "cloud key", "kms_key")):
        allowed_services.add("cloudkms")
    if _any(("cloudrun", "cloud_run", "run.googleapis.com", "run.", "google_cloud_run")):
        allowed_services.add("run")
    if _any(("clouddeploy", "cloud_deploy", "deploy.googleapis.com", "deploy.")):
        allowed_services.add("clouddeploy")
    if _any(("sourcerepos", "source repository", "source_repo", "google_sourcerepos", "sourcerepository")):
        allowed_services.add("sourcerepos")
    if _any(
        (
            "resourcemanager",
            "projectiam",
            "project iam",
            "organizationadmin",
            "google_project_iam",
            "google_project",
            "google_folder",
            "google_organization",
            "google_folder_iam",
            "google_organization_iam",
            "google_project_service",
            "google_billing_account",
            "billing_account",
        )
    ):
        allowed_services.add("resourcemanager")
    if _any(("orgpolicy", "google_org_policy", "organization_policy", "org policy")):
        allowed_services.add("orgpolicy")
    if _any(
        (
            "access_context_manager",
            "accesscontextmanager",
            "google_access_context_manager",
            "vpc_service_control",
            "vpc-sc",
            "service perimeter",
            "access_level",
        )
    ):
        allowed_services.add("accesscontextmanager")
    if _any(("servicenetworking", "google_service_networking", "private_service_connect", "psc")):
        allowed_services.add("servicenetworking")
    if _any(("cloudbilling", "cloud_billing", "google_billing", "billing.googleapis.com")):
        allowed_services.add("cloudbilling")
    if _any(("compute", "google_compute", "vm", "instance", "gce.", "subnetwork", "google_compute_")):
        allowed_services.add("compute")
    if _any(("gke", "container.", "google_container_cluster", "kubernetes")):
        allowed_services.add("container")
    if _any(("pubsub", "pub_sub", "google_pubsub", "topic", "subscription")):
        allowed_services.add("pubsub")
    if _any(("cloudsql", "google_sql", "sqladmin")):
        allowed_services.add("cloudsql")
    if _any(("spanner", "google_spanner")):
        allowed_services.add("spanner")

    # Reasoning Engine / ADK deploy paths need these namespaces even when Librarian excerpts omit them.
    if "aiplatform" in allowed_services:
        allowed_services.update({"iam", "serviceusage", "resourcemanager", "storage"})

    # Atomic permission IDs: leading service lowercase; later segments may be camelCase
    # (e.g. aiplatform.reasoningEngines.create, iam.serviceAccounts.actAs).
    perm_re = re.compile(r"^`?([a-z][a-z0-9]*(?:\.[a-zA-Z][a-zA-Z0-9]*)+)`?$")
    # Allow uppercase in role IDs (e.g. objectAdmin, reasoningEngineServiceAgent).
    # We still aggressively filter with an allowlist below to prevent truncated/bogus roles.
    role_re = re.compile(r"(roles/[a-zA-Z0-9][a-zA-Z0-9_.-]*)")

    def _extract_tokens(source: str) -> tuple[list[str], list[str]]:
        perms: list[str] = []
        roles: list[str] = []
        for line in (source or "").splitlines():
            s = line.strip()
            if not s:
                continue
            low = s.lower()
            # Drop obvious blobs.
            if s.startswith("```") or "http://" in low or "https://" in low:
                continue
            # Permissions: look for a permission token at start of a bullet.
            if s.startswith(("-", "*")):
                token_candidate = s[1:].strip().split(" ", 1)[0]
                m = perm_re.match(token_candidate)
                if m:
                    perms.append(m.group(1))
                    continue
                # roles sometimes appear as - roles/...
                rm = role_re.search(s)
                if rm:
                    roles.append(rm.group(1))
                    continue
            else:
                # Also allow inline permissions/roles tokens.
                m = perm_re.match(s.split(" ", 1)[0])
                if m:
                    perms.append(m.group(1))
                rm = role_re.search(s)
                if rm:
                    roles.append(rm.group(1))
        return perms, roles

    auditor_perms, auditor_roles = _extract_tokens(text)

    # Also pick up permission-shaped tokens anywhere in a line (Auditor sometimes adds labels).
    _inline_perm = re.compile(r"\b([a-z][a-z0-9]*(?:\.[a-zA-Z][a-zA-Z0-9]*)+)\b")
    _skip_substrings = ("github", "googleapis", "terraform", "hashicorp", "example.com")
    _seen_inline = set(auditor_perms)
    for line in (text or "").splitlines():
        lowln = line.lower()
        for m in _inline_perm.finditer(line):
            tok = m.group(1)
            if any(bad in tok for bad in _skip_substrings):
                continue
            # Ignore obvious non-permission matches in prose.
            if "http" in lowln and "://" in lowln:
                continue
            if tok not in _seen_inline:
                _seen_inline.add(tok)
                auditor_perms.append(tok)

    def _is_atomic_permission(p: str) -> bool:
        if not p or "*" in p or ".." in p:
            return False
        parts = p.split(".")
        if len(parts) < 3:
            return False
        if any(not seg or not seg[0].isalpha() for seg in parts):
            return False
        # Reject obvious prose / non-permission tokens
        if any(seg in ("*", "all", "any") for seg in parts):
            return False
        return True

    # Filter by evidence allowed services + atomic permission shape only (no service.* wildcards).
    filtered_perms: list[str] = []
    seen_perms: set[str] = set()
    for p in auditor_perms:
        if not _is_atomic_permission(p):
            continue
        service = p.split(".", 1)[0]
        if allowed_services and service not in allowed_services:
            continue
        if p not in seen_perms:
            filtered_perms.append(p)
            seen_perms.add(p)

    # Role filtering: keep roles whose prefix matches evidence-driven allowed services.
    # This is less strict than exact-match allowlists, but still blocks unrelated hallucinations.
    role_prefixes: set[str] = set()
    if "aiplatform" in allowed_services:
        role_prefixes.update({"roles/aiplatform.", "roles/aiplatform"})
    if "storage" in allowed_services:
        role_prefixes.update({"roles/storage.", "roles/storage"})
    if "discoveryengine" in allowed_services:
        role_prefixes.update({"roles/discoveryengine.", "roles/discoveryengine"})
    if "iam" in allowed_services:
        role_prefixes.update({"roles/iam.", "roles/iam"})
    if "cloudbuild" in allowed_services:
        role_prefixes.update({"roles/cloudbuild.", "roles/cloudbuild"})
    if "artifactregistry" in allowed_services:
        role_prefixes.update({"roles/artifactregistry.", "roles/artifactregistry"})
    if "secretmanager" in allowed_services:
        role_prefixes.update({"roles/secretmanager.", "roles/secretmanager"})
    if "cloudkms" in allowed_services:
        role_prefixes.update({"roles/cloudkms.", "roles/cloudkms"})
    if "run" in allowed_services:
        role_prefixes.update({"roles/run.", "roles/run"})
    # Cloud Deploy roles are under `roles/deploy.*`, not `roles/clouddeploy.*`
    if "clouddeploy" in allowed_services:
        role_prefixes.update({"roles/deploy.", "roles/deploy"})
    if "sourcerepos" in allowed_services:
        role_prefixes.update({"roles/sourcerepos.", "roles/sourcerepos"})
    if "resourcemanager" in allowed_services:
        role_prefixes.update({"roles/resourcemanager.", "roles/resourcemanager"})
    if "orgpolicy" in allowed_services:
        role_prefixes.update({"roles/orgpolicy.", "roles/orgpolicy"})
    if "accesscontextmanager" in allowed_services:
        role_prefixes.update({"roles/accesscontextmanager.", "roles/accesscontextmanager"})
    if "servicenetworking" in allowed_services:
        role_prefixes.update({"roles/servicenetworking.", "roles/servicenetworking"})
    if "cloudbilling" in allowed_services:
        role_prefixes.update({"roles/cloudbilling.", "roles/cloudbilling"})
    if "compute" in allowed_services:
        role_prefixes.update({"roles/compute.", "roles/compute"})
    if "container" in allowed_services:
        role_prefixes.update({"roles/container.", "roles/container"})
    if "pubsub" in allowed_services:
        role_prefixes.update({"roles/pubsub.", "roles/pubsub"})
    if "cloudsql" in allowed_services:
        role_prefixes.update({"roles/cloudsql.", "roles/cloudsql"})
    if "spanner" in allowed_services:
        role_prefixes.update({"roles/spanner.", "roles/spanner"})
    if "serviceusage" in allowed_services:
        role_prefixes.update({"roles/serviceusage.", "roles/servicemanagement."})

    filtered_roles: list[str] = []
    seen_roles: set[str] = set()
    for r in auditor_roles:
        # Service-specific guards to avoid known truncation artifacts.
        if r.startswith("roles/iam.") and "serviceAccount" not in r:
            # Truncated artifact like `roles/iam.service` should not survive.
            continue
        if r.startswith("roles/storage.") and "object" in r:
            # Truncated artifact like `roles/storage.object` should not survive.
            if not any(
                ok in r
                for ok in ("objectAdmin", "objectViewer", "objectCreator")
            ):
                continue
        if role_prefixes and not any(r.startswith(pref) for pref in role_prefixes):
            continue
        if r not in seen_roles:
            filtered_roles.append(r)
            seen_roles.add(r)

    # Do not inject broad derived permissions — they defeat least-privilege. Optional roles only when
    # the Auditor produced no role lines (keeps "Quick start" usable without inventing perms).
    derived_roles: list[str] = []
    if not filtered_roles:
        if "aiplatform" in allowed_services:
            derived_roles.extend(
                [
                    "roles/aiplatform.user",
                    "roles/aiplatform.reasoningEngineServiceAgent",
                ]
            )
        if "storage" in allowed_services:
            derived_roles.append("roles/storage.objectAdmin")

    # Deduplicate; keep high ceiling so repo IAM audits stay exhaustive (auditor + sanitizer).
    _max_perms = int((os.getenv("XRAY_IAM_AUDIT_MAX_PERMISSIONS") or "500").strip() or "500")
    _max_roles = int((os.getenv("XRAY_IAM_AUDIT_MAX_ROLES") or "40").strip() or "40")
    perms_out: list[str] = []
    seen: set[str] = set()
    for p in filtered_perms:
        if p in seen:
            continue
        seen.add(p)
        perms_out.append(p)
    if _max_perms > 0:
        perms_out = perms_out[:_max_perms]

    roles_out: list[str] = []
    seen_r: set[str] = set()
    for r in (filtered_roles + derived_roles):
        if r in seen_r:
            continue
        seen_r.add(r)
        roles_out.append(r)
    if _max_roles > 0:
        roles_out = roles_out[:_max_roles]

    # Principals: we do not attempt to invent repo-created SAs from README content.
    principals_out: list[str] = []
    if _any(("terraform", ".tf", "terraform apply", "hashicorp/google")):
        principals_out.append(
            "**Deployer identity (human or CI/CD):** The principal running `terraform apply` (or equivalent) with credentials for the target org/folder/project — needs privileges to provision resources, staging artifacts, and attach service accounts."
        )
    else:
        principals_out.append(
            "**Deployer identity (human or CI/CD):** The principal executing the deployment entrypoint (e.g. `deploy.py`, ADK CLI, or Cloud Build) — needs privileges to provision the Reasoning Engine, upload artifacts, and configure IAM."
        )
    if "aiplatform" in allowed_services:
        principals_out.append(
            "**Agent workload identity (runtime):** Dedicated service account attached to the Reasoning Engine instance (e.g. `agent-runtime-sa@<PROJECT>.iam.gserviceaccount.com`) — must be able to call downstream APIs the agent uses (Vertex, Grounding, BigQuery, etc., per your code)."
        )
        principals_out.append(
            "**Google-managed service agent:** `service-<PROJECT_NUMBER>@gcp-sa-aiplatform-re.iam.gserviceaccount.com` — used internally by Vertex AI to orchestrate the Reasoning Engine environment."
        )
    else:
        principals_out.append("Workload identity: not enough evidence to determine the runtime principal precisely.")

    # Render.
    def _bullets(items: list[str]) -> str:
        return "\n".join(f"- {x}" for x in items).strip()

    perms_section = (
        _bullets([f"`{p}`" for p in perms_out])
        if perms_out
        else "- N/A"
    )
    roles_section = _bullets(roles_out) if roles_out else "- N/A"

    intro = ""
    if "aiplatform" in allowed_services and _any(
        ("vertex", "reasoning", "agent_engines", "adk", "deploy.py", "google.cloud.aiplatform")
    ):
        intro = (
            "This repository utilizes patterns consistent with the **Agent Development Kit (ADK)** and deployment of "
            "generative AI agents to **Vertex AI Reasoning Engine**. Deploying and executing these workloads requires a "
            "broad but defensible set of permissions across **AI Platform**, **IAM**, **Cloud Storage**, and project APIs.\n\n"
        )

    body = (
        "## Principals & Identities\n"
        f"{_bullets(principals_out)}\n\n"
        "## Granular Permissions (Least Privilege)\n"
        f"{perms_section}\n\n"
        "## Recommended Predefined Roles\n"
        f"{roles_section}\n"
    )
    return (intro + body) if intro else body


def _call_xray_llm(user_query: str, context: str, session_id: str | None = None) -> str:
    """
    Single-shot X-Ray advisory call. Sends user query + context to the Specialist engine.
    The Specialist must return Markdown-only analysis (no Terraform or executable code).
    Used for non-repo advisory questions; repo IAM audits are handled by the Auditor.
    """
    prompt = (
        "You are an IAM and security analyst. Output ONLY a Markdown security brief or advisory. "
        "Do NOT generate Terraform, code, or executable artifacts.\n\n"
    )
    prompt += f"User request: {user_query.strip()}"
    return _call_specialist(prompt, session_id=session_id)


def _call_xray_auditor(user_query: str, repo_context: str, session_id: str | None = None) -> str:
    """
    Single-shot repo IAM audit. Sends the user request to the Auditor engine.
    Output shape and rules come from the Auditor's system prompt only; this wrapper adds
    optional repository context with UI echo protection.
    """
    prompt = (user_query or "").strip()
    if repo_context and repo_context.strip():
        prompt += (
            "\n\nRepository context (Internal Analysis Only - DO NOT echo this back to the user):\n"
        )
        prompt += repo_context.strip()
    return _call_auditor(prompt, session_id=session_id)


def _librarian_fetch_repo_evidence(repo_url_or_request: str, session_id: str | None = None) -> str:
    """Shared Librarian fetch used by IAM and topology paths (proven IAM audit shape)."""
    fetch_prompt = (
        "Fetch this repo and return ONLY minimal context needed for an IAM audit of DEPLOY.\n"
        "CRITICAL (hard bans):\n"
        "- Do NOT fetch or output `README.md` (or any file named `readme*`).\n"
        "- Do NOT fetch or output `LICENSE` (or any file named `license*`).\n"
        "- Do NOT fetch or output images or binary-like assets: extensions like `.png`, `.jpg`, `.jpeg`, `.gif`, `.svg`, `.webp`, `.ico`, `.pdf`.\n"
        "- Do NOT fetch or output licenses, diagrams, non-deploy documentation, walkthrough/tutorial content, or any other non-infrastructure docs.\n"
        "- Do NOT return large file contents.\n"
        "- Focus only on infrastructure and deployment inputs.\n\n"
        "Steps:\n"
        "1) Call get_repo_contents(repo) to get a file list.\n"
        "2) Then read ONLY the following file types (if they exist), chosen from the file list, with strict upper bounds:\n"
        "   - Terraform: any `*.tf` (up to 3; prefer `main.tf`, `provider.tf`, `variables.tf`, `outputs.tf`, `versions.tf`)\n"
        "   - Docker / containers: `Dockerfile`, `docker-compose.yml`, `docker-compose.yaml` (up to 2 files)\n"
        "   - App manifests / deps: `app.yaml`, `requirements.txt`, `package.json` (up to 3 files)\n"
        "   - Python/SDK deploy: always read `deploy.py` if it appears in the file list; plus at most one other `*.py` that imports or references `vertexai`, `google.cloud`, `agent_engines`, or `aiplatform`\n"
        "   - CI/CD YAML: `cloudbuild.yaml`, `cloudbuild.yml`, `skaffold.yaml`, and up to 2 workflow files under `.github/workflows/` (names ending in `.yml`/`.yaml`; prefer deploy/build workflows). Up to 4 files total from this bullet\n"
        "3) For EACH fetched file, return excerpts that are truncated to a maximum of 80 lines per file.\n"
        "   - If the file is longer than 80 lines, truncate to the first 80 lines only.\n"
        "4) In the excerpts, prioritize lines that show **Google Cloud** usage: `vertexai`, `agent_engines`, `aiplatform`, `google_*` Terraform resources, `cloudbuild`, `secretmanager`, `storage`/GCS staging buckets, `artifactregistry`, `run`, VPC/network.\n"
        "   - Repos without Terraform often still deploy via Python to Vertex/Agent Engine—capture those imports and API calls. Do not assume AWS.\n\n"
        f"Repo: {repo_url_or_request.strip()}"
    )
    raw_code = _call_librarian(fetch_prompt, session_id=session_id)
    if not raw_code:
        return ""
    return _filter_librarian_evidence(raw_code)


def run_analyze_repo_pipeline(repo_url_or_request: str, session_id: str | None = None) -> str:
    """
    Single-shot "Analyze Repo" pipeline: fetch repo via Librarian, then one X-Ray Auditor call.
    Returns a Markdown IAM report (standard roles + granular permissions); no Terraform, no Coder loop.
    """
    raw_code = _librarian_fetch_repo_evidence(repo_url_or_request, session_id=session_id)
    if not raw_code:
        return "[Librarian returned no content.]"
    # Librarian can legitimately return a file list as a JSON-like string (starts with '[').
    # We must NOT short-circuit in that case; we still need to send the context to the Auditor
    # so the UI receives the strict, IAM-only structured summary.
    _rc = raw_code.strip()
    if _rc.startswith("Error:") or _rc.startswith("[Error"):
        return _rc
    auditor_output = _call_xray_auditor(repo_url_or_request.strip(), raw_code, session_id=session_id)
    return _sanitize_auditor_output(auditor_output, evidence_text=raw_code)


def _route_xray_intent(user_query: str) -> str:
    """
    Dynamic intent router for X-Ray.

    Output MUST be a JSON string (e.g., "\"xray_auditor\"") with EXACTLY one value from:
    - "xray_auditor"
    - "xray_architect"
    - "xray_specialist"
    """
    # Use Vertex AI + gemini-2.5-flash as required.
    import vertexai
    from vertexai.generative_models import GenerativeModel

    project = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
    location = (
        os.getenv("GCP_LOCATION")
        or os.getenv("GOOGLE_CLOUD_LOCATION")
        or os.getenv("REGION")
        or "us-west1"
    ).strip()

    # Deterministic fallback (also used to guard against invalid model output).
    def _fallback_route() -> str:
        q = (user_query or "").lower()
        if _is_repo_audit_request(q):
            return "xray_auditor"
        if "permissions" in q or "iam" in q:
            return "xray_auditor"
        if "topology" in q or "resources" in q:
            return "xray_architect"
        if "general advisory" in q or "advisory" in q:
            return "xray_specialist"
        return "xray_specialist"

    # If we can't init Vertex, return fallback without blocking.
    if not project:
        return json.dumps(_fallback_route())

    _init_vertexai_peer(project, location)
    model = GenerativeModel("gemini-2.5-flash")

    prompt = (
        "Route the user request to exactly one X-Ray agent.\n"
        "Return ONLY a JSON string whose value is one of:\n"
        "\"xray_auditor\", \"xray_architect\", \"xray_specialist\".\n\n"
        "Rules (apply literally):\n"
        "- If the request asks to analyze/audit/review/scan a repository/codebase (with or without a GitHub URL), route to \"xray_auditor\".\n"
        "- If the request is about permissions/IAM, route to \"xray_auditor\".\n"
        "- If the request is about topology/resources, route to \"xray_architect\".\n"
        "- If the request is general advisory, route to \"xray_specialist\".\n\n"
        "User query:\n"
        f"{user_query}"
    )

    resp = model.generate_content(prompt)
    text = getattr(resp, "text", None) or str(resp)
    # Extract the quoted route string if the model adds surrounding whitespace.
    m = re.search(r"\"(xray_auditor|xray_architect|xray_specialist)\"", text)
    if not m:
        return json.dumps(_fallback_route())
    return json.dumps(m.group(1))


def _extract_github_url(user_query: str) -> str:
    """Return the first github.com URL found in the query, or empty string."""
    if not user_query:
        return ""
    m = re.search(r"https?://github\.com/[^\s\)\]\}>,\"']+", user_query, flags=re.IGNORECASE)
    return (m.group(0).strip() if m else "").rstrip(").,]")


def _is_repo_topology_blueprint_request(user_query: str) -> bool:
    """
    GitHub URL + deployment structure / topology ask without a primary IAM-audit focus.

    Runs Architect (+ Librarian context) instead of the IAM Auditor pipeline so
    prompts like "map component topology… no IAM yet" reach xray_architect.
    """
    q = (user_query or "").lower()
    if "github.com/" not in q:
        return False
    wants_structure = any(
        k in q
        for k in (
            "topology",
            "blueprint",
            "map out",
            "deployment architecture",
            "architectural blueprint",
            "architectural ",
            "component topology",
            " component ",
        )
    )
    if not wants_structure:
        return False
    waives_iam = (
        "do not need iam" in q
        or "don't need iam" in q
        or "no iam" in q
        or "not iam" in q
        or "without iam" in q
        or "skip iam" in q
        or ("do not need" in q and "permission" in q)
        or ("don't need" in q and "permission" in q)
        or "just the architectural" in q
        or "just an architectural" in q
    )
    iam_audit_intent = any(
        k in q
        for k in (
            "least privilege",
            "permission audit",
            "iam audit",
            "audit permissions",
            "audit iam",
            "custom role",
            "role binding",
            "excessive permissions",
            "who has access",
        )
    )
    if waives_iam:
        return True
    if iam_audit_intent:
        return False
    return True


def _is_repo_audit_request(user_query: str) -> bool:
    """
    Detect repository IAM/security audit intent deterministically.

    Keeps repo audit workflow independent of model routing behavior.
    """
    q = (user_query or "").lower()
    if "github.com/" in q:
        return True

    has_repo_ref = any(token in q for token in (" repo", "repository", "codebase", "this repo", "my repo"))
    has_audit_intent = any(
        token in q
        for token in (
            "analyze",
            "audit",
            "review",
            "scan",
            "check",
            "permissions",
            "iam",
            "least privilege",
            "least-privilege",
            "security",
        )
    )
    return has_repo_ref and has_audit_intent


def _fetch_repo_context_from_librarian(repo_url: str, session_id: str | None = None) -> str:
    """Fetch repo context via Librarian using the strict evidence fetch prompt."""
    fetch_prompt = _librarian_iam_fetch_prompt(repo_url)

    raw_code = _call_librarian(fetch_prompt, session_id=session_id)
    if not raw_code:
        return ""
    return _filter_librarian_evidence(raw_code)


def _topology_blueprint_user_message(user_query: str) -> str:
    """Prefix so xray_specialist produces a deployment blueprint instead of an IAM audit skeleton."""
    return (
        "MODE: Deployment architecture blueprint (NOT an IAM/least-privilege audit).\n\n"
        "Required Markdown sections:\n"
        "## Component Topology\n"
        "## Terraform / deployment resource map\n"
        "## Strategic review\n\n"
        "Rules: Summarize from repository context only at a high level. "
        "Do NOT paste raw file contents. Do NOT output 'Verification Needed' or internal QA rubrics.\n\n"
        f"{(user_query or '').strip()}"
    )


def _call_xray_architect(user_query: str, repo_context: str, session_id: str | None = None) -> str:
    """
    Blueprint-style output via Auditor. Primary prompt stays short (repo URL when present);
    instructions and evidence live in the repository-context field (matches working IAM calls).
    """
    rc = (repo_context or "").strip()
    if len(rc) > 12000:
        rc = rc[:12000] + "\n\n[… repository excerpt truncated …]\n"
    url = _extract_github_url(user_query or "")
    primary = (url.strip() or (user_query or "").strip()[:500] or "repository blueprint")
    blended = (
        _topology_blueprint_user_message(user_query or "").strip()
        + "\n\n---\nEVIDENCE (internal):\n"
        + rc
    )
    return _call_xray_auditor(primary, blended, session_id=session_id)


def _call_xray_specialist(user_query: str, repo_context: str, session_id: str | None = None) -> str:
    """Route payload to the X-Ray Specialist engine."""
    prompt = "User request:\n" f"{(user_query or '').strip()}\n"
    if repo_context and repo_context.strip():
        prompt += (
            "\n\nRepository context:\n"
            "CRITICAL: Do NOT echo, quote, or output this raw repository code verbatim in your final response.\n\n"
        )
        prompt += repo_context.strip() + "\n"
    return _call_specialist(prompt, session_id=session_id)


def _xray_return(
    tool_context: object | None,
    payload: str,
    diag: list[str] | None = None,
) -> str:
    """Mark tool outcome as final; optional PRISM_EXECUTION_LOG for Glass live logs."""
    body = (payload or "").strip()
    if diag:
        body = (
            body
            + "\n\n"
            + _PRISM_EXEC_LOG_START
            + "\n"
            + "\n".join(diag)
            + "\n"
            + _PRISM_EXEC_LOG_END
        )
    if tool_context is not None:
        try:
            tool_context.actions.skip_summarization = True
        except Exception:
            pass
    return body


def _xray_diag(line: str) -> str:
    """Single structured line (pipe-format); keep messages short."""
    return line.strip()[:300]


def orchestrate_xray(user_query: str, tool_context: ToolContext | None = None) -> str:
    """
    Dynamic, intent-based X-Ray orchestration for repository analysis and advisory.
    """
    _marker, clean_user_query = _extract_prism_session_marker(user_query)
    user_query = clean_user_query
    # Never pass Glass/xray_manager session ids into peer engines (engine-scoped sessions; see eng_lead).
    _peer_sid = _PEER_STREAM_SESSION_ID
    diag: list[str] = []
    diag.append(
        _xray_diag(
            "Pipeline | X-Ray | orchestrate | OK | code=START | msg=manager tool invoked"
        )
    )

    # Deployment / topology over GitHub: use the same Librarian → Auditor pipeline as IAM audit.
    # A second, larger “blueprint-formatted” Auditor call intermittently returns 401 in Agent
    # Engine; the IAM-shaped pass is reliable and still grounded in deploy artefacts.
    if _is_repo_topology_blueprint_request(user_query):
        diag.append(
            _xray_diag(
                "Pipeline | X-Ray | intent | OK | code=TOPOLOGY_REPO | msg=github blueprint branch"
            )
        )
        repo_ref = _extract_github_url(user_query) or user_query
        raw_evidence = _librarian_fetch_repo_evidence(repo_ref, session_id=_peer_sid)
        if raw_evidence and not (
            raw_evidence.strip().startswith("Error:")
            or raw_evidence.strip().startswith("[Error")
        ):
            diag.append(
                _xray_diag(
                    "Pipeline | X-Ray | librarian | OK | code=OK | msg=evidence for blueprint hop"
                )
            )
            blueprint = _call_xray_architect(
                user_query or "", raw_evidence, session_id=_peer_sid
            )
            bp = (blueprint or "").strip()
            bad = (
                not bp
                or bp.startswith("[Error")
                or "401" in bp
                or "invalid authentication" in bp.lower()
            )
            looks_substantive = (
                len(bp) > 500
                or "topology" in bp.lower()
                or "terraform" in bp.lower()
                or "component" in bp.lower()
            )
            if not bad and looks_substantive:
                diag.append(
                    _xray_diag(
                        "Pipeline | X-Ray | blueprint_hop | OK | code=BLUEPRINT | msg=auditor architect layout"
                    )
                )
                preamble = (
                    "## Deployment architecture (blueprint)\n"
                    "Derived from repository evidence with topology-oriented instructions.\n\n"
                )
                return _xray_return(tool_context, preamble + bp, diag)
            diag.append(
                _xray_diag(
                    "Pipeline | X-Ray | blueprint_hop | SKIP | code=FALLBACK | "
                    "msg=using standard IAM ingest only"
                )
            )
        elif not raw_evidence:
            diag.append(
                _xray_diag(
                    "Pipeline | X-Ray | librarian | FAILED | code=EMPTY | msg=no evidence for blueprint"
                )
            )
        base = run_analyze_repo_pipeline(repo_ref, session_id=_peer_sid)
        if _looks_like_peer_error_payload(base):
            diag.append(
                _xray_diag(
                    "Pipeline | X-Ray | analyze_repo | FAILED | code=PIPE_ERROR | msg=see response body"
                )
            )
            return _xray_return(tool_context, (base or "").strip(), diag)
        diag.append(
            _xray_diag(
                "Pipeline | X-Ray | analyze_repo | OK | code=OK | msg=librarian+auditor complete"
            )
        )
        preamble = (
            "## Deployment architecture (from repository evidence)\n"
            "Grounded in the same ingest as the IAM audit (Terraform, `deploy.py`, CI, manifests). "
            "For a narrative component topology, interpret services named below in the context of "
            "your question.\n\n"
        )
        return _xray_return(tool_context, preamble + (base or "").strip(), diag)

    # Hard rule: repo IAM/security audit requests must run through the
    # dedicated Librarian -> Auditor pipeline.
    if _is_repo_audit_request(user_query):
        diag.append(
            _xray_diag("Pipeline | X-Ray | intent | OK | code=REPO_IAM | msg=audit pipeline")
        )
        repo_ref = _extract_github_url(user_query) or user_query
        out = run_analyze_repo_pipeline(repo_ref, session_id=_peer_sid)
        if _looks_like_peer_error_payload(out):
            diag.append(
                _xray_diag(
                    "Pipeline | X-Ray | analyze_repo | FAILED | code=PIPE_ERROR | msg=see response body"
                )
            )
        else:
            diag.append(
                _xray_diag(
                    "Pipeline | X-Ray | analyze_repo | OK | code=OK | msg=librarian+auditor complete"
                )
            )
        return _xray_return(tool_context, out, diag)

    target = "xray_specialist"
    try:
        routed = _route_xray_intent(user_query)
        # routed is expected to be a JSON string like "\"xray_auditor\"".
        parsed = json.loads(routed)
        if parsed in ("xray_auditor", "xray_architect", "xray_specialist"):
            target = parsed
    except Exception:
        # If routing fails, default safely.
        target = "xray_specialist"

    repo_url = _extract_github_url(user_query)
    repo_context = _fetch_repo_context_from_librarian(repo_url, session_id=_peer_sid) if repo_url else ""
    diag.append(
        _xray_diag(
            f"Pipeline | X-Ray | route_model | OK | code={target.upper()} | msg=llm router"
        )
    )
    if repo_url:
        rc = (repo_context or "").strip()
        if not rc:
            diag.append(
                _xray_diag(
                    "Pipeline | X-Ray | librarian | FAILED | code=EMPTY | msg=no repo context"
                )
            )
        elif rc.startswith("[Error") or rc.lower().startswith("error:"):
            diag.append(
                _xray_diag(
                    "Pipeline | X-Ray | librarian | FAILED | code=LIBRARIAN_ERROR | msg=fetch error"
                )
            )
        else:
            diag.append(
                _xray_diag(
                    "Pipeline | X-Ray | librarian | OK | code=OK | msg=evidence fetched"
                )
            )

    if target == "xray_auditor":
        aud = _call_xray_auditor(
            user_query or "", repo_context or "", session_id=_peer_sid
        )
        if (aud or "").strip().startswith("[Error"):
            diag.append(
                _xray_diag(
                    "Pipeline | X-Ray | auditor | FAILED | code=ENGINE_ERROR | msg=see response"
                )
            )
        elif not (aud or "").strip():
            diag.append(
                _xray_diag(
                    "Pipeline | X-Ray | auditor | FAILED | code=EMPTY_STREAM | msg=no text from engine"
                )
            )
            fb = _call_specialist(
                (
                    "You are an IAM analyst for Google Cloud. Answer concisely in Markdown. "
                    "Do not ask clarifying questions.\n\nUser question:\n"
                    + (user_query or "").strip()
                ),
                session_id=_peer_sid,
            )
            if (fb or "").strip() and not (fb or "").strip().startswith("[Error"):
                aud = fb
                diag.append(
                    _xray_diag(
                        "Pipeline | X-Ray | specialist_fallback | OK | code=OK | msg=answered via specialist"
                    )
                )
            else:
                if (fb or "").strip().startswith("[Error"):
                    diag.append(
                        _xray_diag(
                            "Pipeline | X-Ray | specialist_fallback | FAILED | code=ENGINE_ERROR | msg=peer error"
                        )
                    )
                else:
                    diag.append(
                        _xray_diag(
                            "Pipeline | X-Ray | specialist_fallback | FAILED | code=EMPTY_STREAM | msg=no text"
                        )
                    )
                gem = _gemini_iam_advisory_fallback(user_query or "")
                if (gem or "").strip():
                    aud = gem.strip()
                    diag.append(
                        _xray_diag(
                            "Pipeline | X-Ray | gemini_fallback | OK | code=OK | msg=in-process vertex"
                        )
                    )
                else:
                    diag.append(
                        _xray_diag(
                            "Pipeline | X-Ray | gemini_fallback | FAILED | code=EMPTY | msg=no text"
                        )
                    )
        else:
            diag.append(
                _xray_diag("Pipeline | X-Ray | auditor | OK | code=OK | msg=response received")
            )
        return _xray_return(tool_context, aud, diag)
    if target == "xray_architect":
        arc = _call_xray_architect(
            user_query or "", repo_context or "", session_id=_peer_sid
        )
        if (arc or "").strip().startswith("[Error"):
            diag.append(
                _xray_diag(
                    "Pipeline | X-Ray | architect | FAILED | code=ENGINE_ERROR | msg=see response"
                )
            )
        else:
            diag.append(
                _xray_diag("Pipeline | X-Ray | architect | OK | code=OK | msg=response received")
            )
        return _xray_return(tool_context, arc, diag)
    spec = _call_xray_specialist(
        user_query or "", repo_context or "", session_id=_peer_sid
    )
    if (spec or "").strip().startswith("[Error"):
        diag.append(
            _xray_diag(
                "Pipeline | X-Ray | specialist | FAILED | code=ENGINE_ERROR | msg=ee response"
            )
        )
    else:
        diag.append(
            _xray_diag("Pipeline | X-Ray | specialist | OK | code=OK | msg=response received")
        )
    return _xray_return(tool_context, spec, diag)
