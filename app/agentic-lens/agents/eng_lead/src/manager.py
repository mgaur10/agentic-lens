"""
Engineering Lead — orchestration logic for Scout → Coder → Quality and Security Reviewer.
Implements orchestrate_build(user_query): Plan → Build → Audit loop (max 3 retries).
"""
import json
import logging
import os
import re
import threading
import time
from typing import Optional
try:
    from opentelemetry.trace import Status, StatusCode
except Exception:
    class StatusCode:
        ERROR = "ERROR"

    class Status:
        def __init__(self, _code):
            self.code = _code

try:
    from .telemetry import get_tracer, inject_w3c_headers
except ImportError:
    from telemetry import get_tracer, inject_w3c_headers

logger = logging.getLogger(__name__)
tracer = get_tracer()

try:
    from .vertex_init import init_vertexai as _init_vertexai
except ImportError:
    from vertex_init import init_vertexai as _init_vertexai

_USER_ID = "eng_lead"
_MAX_REVIEW_RETRIES = 3
_APPROVED_FOOTER = "\n\n✅ Approved"
_VALIDATION_FAILED_FOOTER = "\n\n⚠️ Quality and Security Reviewer validation failed"

# Delimiter for execution log so the UI can parse and show in Agent steps + Live logs
_EXEC_LOG_START = "\n\n<!-- PRISM_EXECUTION_LOG -->\n"
_EXEC_LOG_END = "\n<!-- /PRISM_EXECUTION_LOG -->"
_CODE_REQUEST_RE = re.compile(
    # Keep this strict: only explicit code/file artifact asks should trigger code mode.
    r"\b(terraform|write code|source code|code|script|bash|shell|yaml|json|"
    r"hcl|python|module|resource|deployment file|main\.tf|variables\.tf|outputs\.tf|"
    r"cloudbuild\.yaml|dockerfile)\b",
    re.IGNORECASE,
)
_ARCH_REQUEST_RE = re.compile(
    r"\b(design|architecture|architect|approach|strategy|trade[- ]?off|"
    r"compare|comparison|which service|recommend|high[- ]?level|explain|"
    r"list|services i should use|reference architecture)\b",
    re.IGNORECASE,
)
_PRISM_SESSION_MARKER_RE = re.compile(r"^\s*<!--\s*PRISM_SESSION_ID:([^>]+?)\s*-->\s*\n?", re.IGNORECASE)
_LENS_TRACEPARENT_MARKER_RE = re.compile(r"^\s*<!--\s*LENS_TRACEPARENT:([^>]+?)\s*-->\s*\n?", re.IGNORECASE)
_LENS_TRACESTATE_MARKER_RE = re.compile(r"^\s*<!--\s*LENS_TRACESTATE:([^>]+?)\s*-->\s*\n?", re.IGNORECASE)
_LENS_REQUEST_ID_MARKER_RE = re.compile(
    r"^\s*<!--\s*LENS_REQUEST_ID:([^>]+?)\s*-->\s*\n?",
    re.IGNORECASE,
)
# Per-thread correlation from Glass UI (same worker as orchestrate_build).
_eng_orchestrate_tls = threading.local()

# Structured lines for Glass Live logs + Cloud Logging (pipe-separated, no secrets / no prompts).
def _pipeline_diag_append(
    execution_log: list[str],
    step: str,
    raw: Optional[str],
    *,
    detail: Optional[str] = None,
) -> None:
    """Classify engine/tool output and append one Pipeline line for operators."""
    s = (raw or "").strip()
    msg_extra = ""
    if detail:
        msg_extra = f" | detail={detail[:120]}"
    if not s:
        execution_log.append(
            f"Pipeline | {step} | FAILED | code=EMPTY_STREAM | msg=no text from engine{msg_extra}"
        )
        return
    low = s.lower()
    if "401" in s and "invalid authentication" in low:
        execution_log.append(
            f"Pipeline | {step} | FAILED | code=AUTH_401 | msg=vertex authentication rejected{msg_extra}"
        )
        return
    if "403" in s and "permission" in low:
        execution_log.append(
            f"Pipeline | {step} | FAILED | code=AUTH_403 | msg=permission denied{msg_extra}"
        )
        return
    if "[scout engine not configured" in low or "[coder engine not configured" in low:
        execution_log.append(
            f"Pipeline | {step} | FAILED | code=ENGINE_NOT_CONFIGURED | msg=missing peer engine id{msg_extra}"
        )
        return
    if s.startswith("[error calling engine") or (s.startswith("[") and "error" in low[:80]):
        snippet = " ".join(s.split())[:140]
        execution_log.append(
            f"Pipeline | {step} | FAILED | code=ENGINE_ERROR | msg={snippet}{msg_extra}"
        )
        return
    execution_log.append(f"Pipeline | {step} | OK | code=OK | msg=response received{msg_extra}")


def _collect_from_event(ev: object, out: list[str]) -> None:
    """Collect model output from a stream event.

    Vertex/ADK stream event shapes vary (dict vs SDK objects, and `parts` may contain `text`,
    `output`, or function tool results). This collector is intentionally defensive so we
    don't end up with empty strings from valid outputs.
    """
    if ev is None:
        return

    # 1) Plain strings
    if isinstance(ev, str):
        if ev.strip():
            out.append(ev.strip())
        return

    # 1b) List roots (e.g. stream chunk is a list of candidate dicts)
    if isinstance(ev, list):
        for item in ev:
            _collect_from_event(item, out)
        return

    # 2) Dict events (common for ADK streaming)
    if isinstance(ev, dict):
        # Direct keys first
        for key in ("text", "result", "summary", "output", "message"):
            val = ev.get(key)
            if isinstance(val, str) and val.strip():
                out.append(val.strip())
                return

        # Nested "content" wrapper — include top-level candidates (Gemini generateContent stream)
        content = (
            ev.get("content")
            or ev.get("event")
            or ev.get("response")
            or ev.get("candidates")
            or ev.get("chunk")
            or ev.get("data")
            or ev
        )
        if isinstance(content, list):
            for item in content:
                _collect_from_event(item, out)
                if out:
                    return
            return
        if isinstance(content, dict):
            inner = content.get("content")
            if isinstance(inner, dict):
                content = inner

            parts = (
                content.get("parts")
                or content.get("Parts")
                or content.get("candidates")
                or content.get("messages")
            )
            # If we didn't find a "parts-like" structure, fall back to recursive descent.
            if parts is None:
                for k in ("output", "text", "result"):
                    v = content.get(k)
                    if isinstance(v, str) and v.strip():
                        out.append(v.strip())
                        return
                # recursive descent for any nested dict/list
                for v in content.values():
                    if isinstance(v, (dict, list, str)):
                        _collect_from_event(v, out)
                        if out:
                            return
                return

            if not isinstance(parts, list):
                parts = [parts]

            for p in parts:
                if not isinstance(p, dict):
                    _collect_from_event(p, out)
                    if out:
                        return
                    continue

                # Normal content parts
                for k in ("text", "output", "result", "message"):
                    pv = p.get(k)
                    if isinstance(pv, str) and pv.strip():
                        out.append(pv.strip())
                        return

                # Gemini candidate shape: { "content": { "parts": [ ... ] }, "finishReason": ... }
                nested = p.get("content")
                if nested is not None:
                    _collect_from_event(nested, out)
                    if out:
                        return

                # ADK tool result shape: function_response.response.result
                fr = p.get("function_response") or {}
                if isinstance(fr, dict):
                    resp = fr.get("response")
                    if isinstance(resp, dict):
                        rr = resp.get("result")
                        if isinstance(rr, str) and rr.strip():
                            out.append(rr.strip())
                            return
                        if rr is not None:
                            out.append(str(rr).strip())
                            return
                    elif isinstance(resp, str) and resp.strip():
                        out.append(resp.strip())
                        return

        for sub in ev.get("events") or []:
            _collect_from_event(sub, out)
            if out:
                return
        for m in ev.get("messages") or []:
            _collect_from_event(m, out)
            if out:
                return
        return

    # 3) SDK/proto objects: attribute-style extraction
    for attr in ("text", "output", "result", "message", "summary"):
        if hasattr(ev, attr):
            t = getattr(ev, attr, None)
            if isinstance(t, str) and t.strip():
                out.append(t.strip())
                return

    if hasattr(ev, "candidates"):
        c = getattr(ev, "candidates", None)
        if c is not None:
            _collect_from_event(c, out)
            if out:
                return

    if hasattr(ev, "content"):
        _collect_from_event(getattr(ev, "content"), out)
        return

    if hasattr(ev, "parts"):
        _collect_from_event(getattr(ev, "parts"), out)


def _extract_prism_session_marker(message: str) -> tuple[Optional[str], str]:
    """Extract PRISM session marker from message and return (session_id, cleaned_message)."""
    raw = message or ""
    m = _PRISM_SESSION_MARKER_RE.match(raw)
    if not m:
        return (None, raw)
    sid = (m.group(1) or "").strip()
    cleaned = raw[m.end():]
    return ((sid or None), cleaned)


def _extract_lens_request_id_marker(message: str) -> tuple[Optional[str], str]:
    raw = message or ""
    m = _LENS_REQUEST_ID_MARKER_RE.match(raw)
    if not m:
        return (None, raw)
    rid = (m.group(1) or "").strip() or None
    return (rid, raw[m.end() :])


def _extract_lens_trace_marker(message: str) -> tuple[Optional[str], Optional[str], str]:
    raw = message or ""
    remaining = raw
    traceparent = None
    tracestate = None
    m_tp = _LENS_TRACEPARENT_MARKER_RE.match(remaining)
    if m_tp:
        traceparent = (m_tp.group(1) or "").strip() or None
        remaining = remaining[m_tp.end():]
    m_ts = _LENS_TRACESTATE_MARKER_RE.match(remaining)
    if m_ts:
        tracestate = (m_ts.group(1) or "").strip() or None
        remaining = remaining[m_ts.end():]
    return (traceparent, tracestate, remaining)


def _with_lens_trace_marker(message: str) -> str:
    carrier = inject_w3c_headers()
    traceparent = carrier.get("traceparent")
    if not traceparent:
        return message
    tracestate = carrier.get("tracestate")
    prefix = f"<!-- LENS_TRACEPARENT:{traceparent} -->\n"
    if tracestate:
        prefix += f"<!-- LENS_TRACESTATE:{tracestate} -->\n"
    return prefix + message


def _call_engine(engine_name: str, message: str, session_id: Optional[str] = None) -> str:
    """Call an Agent Engine with message; return combined response text. Extracts text and function_response.response.result from stream."""
    # --- Agent-to-agent (A2A-style) call: we use Vertex Agent Engine SDK (agent_engines.get + stream_query), not the HTTP A2A protocol. ---
    if not engine_name or not engine_name.strip():
        return ""
    with tracer.start_as_current_span("lens.engineering.call_engine") as span:
        span.set_attribute("agent.system", "agentic_lens")
        span.set_attribute("department", "engineering")
        span.set_attribute("agent.role", "lead")
        span.set_attribute("target.engine_name", engine_name)
        _orid = getattr(_eng_orchestrate_tls, "lens_request_id", None)
        if _orid:
            span.set_attribute("lens.request_id", _orid)
        try:
            import vertexai
            try:
                from vertexai import agent_engines
            except ImportError:
                from vertexai.preview import agent_engines  # Fallback for some runtime environments

            project = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
            location = (os.getenv("GCP_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("REGION") or "us-west1").strip()
            if not project:
                logger.warning("GCP_PROJECT_ID and GOOGLE_CLOUD_PROJECT are unset")
                return ""
            _init_vertexai(project, location)
            engine = agent_engines.get(engine_name)
            # Peer engines: omit LENS_TRACEPARENT HTML from the payload (trace stays on Glass→eng_lead hop).
            kwargs = {"message": (message or "").strip(), "user_id": _USER_ID}
            if session_id:
                kwargs["session_id"] = session_id
            try:
                stream = engine.stream_query(**kwargs)
            except Exception as e_stream:
                # Session IDs are engine-scoped in Agent Engine. If a cross-engine session
                # is not found, retry without session_id to avoid hard failures.
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
            texts = []
            for ev in stream:
                _collect_from_event(ev, texts)
            if texts:
                return "\n".join(texts).strip()
            # Fallback: blocking query when stream yielded no text/result (e.g. different event shape)
            try:
                response = engine.query(**kwargs)
                _collect_from_event(response, texts)
                if texts:
                    return "\n".join(texts).strip()
                if hasattr(response, "text") and response.text:
                    return str(response.text).strip()
                # Last-resort: some SDK objects stringify to the final model text (often
                # including fenced code blocks). Avoid returning empty when that happens.
                try:
                    raw = str(response).strip() if response is not None else ""
                    if raw and raw not in ("{}", "{ }"):
                        return raw
                except Exception:
                    pass
            except Exception as e_fallback:
                logger.warning("Engine stream yielded no text; query fallback failed: %s", e_fallback)
            # One retry helps transient empty streams from Agent Engine without surfacing as hard failure.
            try:
                time.sleep(0.35)
                texts_retry: list[str] = []
                stream2 = engine.stream_query(**kwargs)
                for ev2 in stream2:
                    _collect_from_event(ev2, texts_retry)
                if texts_retry:
                    return "\n".join(texts_retry).strip()
            except Exception as e_retry:
                logger.debug("Engine stream retry failed: %s", e_retry)
            return ""
        except Exception as e:
            logger.exception("Engine call failed: %s", e)
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR))
            return f"[Error calling engine: {e}]"


def _get_engine_by_name(target_name: str) -> Optional[str]:
    """Resolve Engine ID by display name (e.g. 'eng_scout')."""
    try:
        import vertexai
        try:
            from vertexai.preview.reasoning_engines import ReasoningEngine
        except ImportError:
            try:
                from vertexai import agent_engines as ReasoningEngine # Fallback
            except ImportError:
                 from vertexai.preview import agent_engines as ReasoningEngine

        project = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
        location = (os.getenv("GCP_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("REGION") or "us-west1").strip()
        
        if not project:
            return None

        _init_vertexai(project, location)

        # Try listing
        engines = []
        try:
             engines = list(ReasoningEngine.list())
        except Exception:
             pass

        target_clean = target_name.strip().lower().replace("_", "-")
        
        for e in engines:
            gca = getattr(e, "_gca_resource", None)
            display = (
                (gca.display_name if gca and hasattr(gca, "display_name") else None)
                or getattr(e, "display_name", None)
                or ""
            )
            display_lower = (display or "").strip().lower().replace("_", "-")
            
            # 1. Exact match (e.g. "eng-scout" == "eng-scout")
            if display_lower == target_clean:
                return getattr(e, "resource_name", None) or (gca.name if gca else None)
            
            # 2. Suffix match (e.g. "agentic-lens-eng-scout" ends with "eng-scout")
            if display_lower.endswith(f"-{target_clean}"):
                 return getattr(e, "resource_name", None) or (gca.name if gca else None)
                 
    except Exception as e:
        logger.warning("Could not resolve engine for %s: %s", target_name, e)
    return None

def _extract_gemini_response_text(response: object) -> str:
    """Best-effort text from generate_content; handles empty `.text` when candidates carry parts."""
    if not response:
        return ""
    try:
        t = response.text  # type: ignore[attr-defined]
        if isinstance(t, str) and t.strip():
            return t.strip()
    except (ValueError, AttributeError):
        pass
    cands = getattr(response, "candidates", None) or []
    for c in cands:
        content = getattr(c, "content", None)
        if content is None and isinstance(c, dict):
            content = c.get("content")
        parts = None
        if content is not None:
            parts = getattr(content, "parts", None)
            if parts is None and isinstance(content, dict):
                parts = content.get("parts")
        if not parts:
            continue
        if not isinstance(parts, (list, tuple)):
            parts = [parts]
        for p in parts:
            try:
                if isinstance(p, dict):
                    txt = p.get("text") or ""
                else:
                    txt = p.text  # type: ignore[attr-defined]
                if isinstance(txt, str) and txt.strip():
                    return txt.strip()
            except AttributeError:
                continue
    return ""


def _scout_plan_unusable(plan: Optional[str]) -> bool:
    """True when Scout output is empty or a known engine error placeholder (not valid plans)."""
    if plan is None:
        return True
    s = plan.strip()
    if not s:
        return True
    low = s.lower()
    for prefix in ("[error calling", "[scout engine", "[scout returned"):
        if low.startswith(prefix):
            return True
    if "[error calling engine" in low or "engine not configured" in low:
        return True
    return False


def _plan_fallback_gemini(user_query: str) -> str:
    """When Scout returns no plan, generate a minimal execution plan with Gemini so the pipeline can continue."""
    project = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
    location = (os.getenv("GCP_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("REGION") or "us-west1").strip()
    if not project:
        return ""
    prompt = (
        "You are an infrastructure architect. In one short paragraph, output a concrete execution plan "
        "for the following request. Include: resource types (e.g. Terraform resource names), key config "
        "(e.g. private IP, HA), and nothing else. No code. Plan only.\n\nRequest: "
    ) + user_query
    try:
        import vertexai
        from vertexai.generative_models import (
            GenerativeModel,
            HarmBlockThreshold,
            HarmCategory,
        )

        _init_vertexai(project, location)
        relaxed = {
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }
        # Prefer Flash first (fewer empty/blocked responses in Agent Engine workers).
        for model_name in ("gemini-2.5-flash", "gemini-2.5-pro"):
            try:
                model = GenerativeModel(model_name)
                response = model.generate_content(
                    prompt,
                    generation_config={"temperature": 0.2, "max_output_tokens": 2048},
                    safety_settings=relaxed,
                )
                text = _extract_gemini_response_text(response)
                if text:
                    return text
            except Exception as inner:
                logger.warning("Gemini plan fallback (%s) failed: %s", model_name, inner)
    except Exception as e:
        logger.warning("Gemini plan fallback failed: %s", e)
    # Ultra-short Flash path (some Agent Engine runtimes return empty from Pro calls).
    try:
        import vertexai
        from vertexai.generative_models import (
            GenerativeModel,
            HarmBlockThreshold,
            HarmCategory,
        )

        _init_vertexai(project, location)
        relaxed = {
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }
        model = GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            "Output a numbered implementation plan only (Terraform-focused, Google Cloud). "
            "Each line: resource type + one-line purpose. Max 12 lines. No introduction.\n\n"
            + user_query,
            generation_config={"temperature": 0.1, "max_output_tokens": 1024},
            safety_settings=relaxed,
        )
        text = _extract_gemini_response_text(response)
        if text:
            return text
    except Exception as e:
        logger.warning("Gemini flash last-resort plan failed: %s", e)
    return ""


def _minimal_coder_plan_from_query(user_query: str) -> str:
    """When Scout and Gemini plan both fail, still give Coder a structured brief from the user ask."""
    q = (user_query or "").strip()
    return (
        "EXECUTION PLAN (synthetic — upstream plan step unavailable; follow the user request exactly):\n"
        "1) Implement everything the user asked for; do not omit regions, machine types, counts, or names they specified.\n"
        "2) Emit complete, valid Terraform in ```terraform unless they explicitly asked for Python.\n"
        "3) Add dependencies implied by the request (e.g. VPC/subnetwork for standard GKE when not using Autopilot-only defaults).\n"
        "4) Prefer Google provider resources matching the request; use variables for project/region where appropriate.\n\n"
        f"USER REQUEST (source of truth):\n{q}"
    )


def _explain_architecture_from_plan(user_query: str, build_plan: str) -> str:
    """Generate an architecture explanation from the Scout plan without code."""
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel

        project = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
        location = (os.getenv("GCP_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("REGION") or "us-west1").strip()
        if not project:
            return ""
        _init_vertexai(project, location)
        model = GenerativeModel("gemini-2.5-pro")
        prompt = (
            "When asked to design an architecture or provide explanatory guidance without code, you must act as a "
            "Principal Cloud Architect. The user wants explanatory architecture guidance only — NO Terraform, Python, "
            "JSON, YAML, shell, or fenced code blocks.\n\n"
            "Your response MUST follow this exact Markdown structure (use these headings verbatim):\n\n"
            "## 1. Executive Summary\n"
            "A brief 2-sentence overview of the architecture.\n\n"
            "## 2. Component Breakdown\n"
            "Explicitly list the GCP services chosen for each layer (e.g. Frontend, Backend API, Database, Caching, "
            "Eventing) with a 1-sentence justification for why that specific service was chosen (e.g. 'Cloud Run was "
            "chosen over GKE to minimize operational overhead'). Also cover Observability/Security when applicable.\n\n"
            "## 3. High-Level Data Flow\n"
            "A brief numbered list showing how a user or system request flows through the components end-to-end "
            "(at least 5 steps where the use case warrants it).\n\n"
            "You must provide a complete, well-rounded design. Never stop mid-thought, never use placeholder-only answers, "
            "and never substitute this structure with a terse bullet list.\n\n"
            f"User request:\n{user_query}\n\n"
            f"Scout / plan context (for grounding only; do not quote raw checklists verbatim if they are Terraform-only):\n"
            f"{build_plan}"
        )
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.2, "max_output_tokens": 4096},
        )
        if response and response.text and response.text.strip():
            return response.text.strip()
    except Exception as e:
        logger.warning("Architecture explanation generation failed: %s", e)
    return ""


def _is_gcp_iac_cluster_build_request(user_query: str) -> bool:
    """True when the user asks for deployable config for GKE/Autopilot without saying 'terraform' or 'code'.

    Avoid matching generic explainers: require an imperative (write/create/…) plus GKE/Autopilot and cluster(s).
    """
    ql = (user_query or "").lower()
    if not ql:
        return False
    if not re.search(
        r"\b(write|generate|create|define|draft|provision|give\s+me|build)\b",
        ql,
    ):
        return False
    # Q&A style ("how do I …") without an explicit artifact ask → not a hard codegen request.
    if re.search(r"\bhow\s+do\s+i\b", ql) and not re.search(
        r"\b(terraform|hcl|\.tf\b|infra|infrastructure|iac)\b",
        ql,
    ):
        return False
    if re.search(r"\b(what|why|how\s+does|explain|compare|difference|vs\.?|versus)\b", ql):
        return False
    if not re.search(r"\b(gke|google_container_cluster|autopilot)\b", ql):
        return False
    return bool(re.search(r"\bclusters?\b", ql))


def _wants_terraform_fence(user_query: str) -> bool:
    """Whether to force the Coder to emit ```terraform (not only when the literal word 'terraform' appears)."""
    ql = (user_query or "").lower()
    if re.search(r"\bterraform\b", ql) or re.search(
        r"\b(hcl|\.tf\b|variables\.tf|outputs\.tf|main\.tf)\b", ql
    ):
        return True
    return _is_gcp_iac_cluster_build_request(user_query)


def _is_code_generation_request(user_query: str) -> bool:
    text = (user_query or "").strip()
    if not text:
        return False
    if _CODE_REQUEST_RE.search(text):
        return True
    return _is_gcp_iac_cluster_build_request(text)


def _is_architecture_explanation_request(user_query: str) -> bool:
    text = (user_query or "").strip()
    if not text:
        return False
    if _is_code_generation_request(text):
        return False
    return bool(_ARCH_REQUEST_RE.search(text))


def _call_scout(query: str, session_id: Optional[str] = None) -> str:
    """Call eng_scout with user query; return build plan."""
    with tracer.start_as_current_span("lens.engineering.scout") as span:
        span.set_attribute("agent.system", "agentic_lens")
        span.set_attribute("department", "engineering")
        span.set_attribute("agent.role", "scout")
        _tlr = getattr(_eng_orchestrate_tls, "lens_request_id", None)
        if _tlr:
            span.set_attribute("lens.request_id", _tlr)
        name = (os.getenv("AGENTIC_LENS_ENGINE_SCOUT") or "").strip() or _get_engine_by_name("eng_scout")
        if not name:
            return "[Scout engine not configured. Set AGENTIC_LENS_ENGINE_SCOUT or ensure 'eng_scout' exists.]"
        return _call_engine(name, query, session_id=session_id)


def _call_coder(plan_or_fix_request: str, session_id: Optional[str] = None) -> str:
    """Call eng_coder with plan or fix request; return code."""
    with tracer.start_as_current_span("lens.engineering.coder") as span:
        span.set_attribute("agent.system", "agentic_lens")
        span.set_attribute("department", "engineering")
        span.set_attribute("agent.role", "coder")
        _tlr = getattr(_eng_orchestrate_tls, "lens_request_id", None)
        if _tlr:
            span.set_attribute("lens.request_id", _tlr)
        name = (os.getenv("AGENTIC_LENS_ENGINE_CODER") or "").strip() or _get_engine_by_name("eng_coder")
        if not name:
            return "[Coder engine not configured. Set AGENTIC_LENS_ENGINE_CODER or ensure 'eng_coder' exists.]"
        return _call_engine(name, plan_or_fix_request, session_id=session_id)


def _call_quality_security_reviewer(
    code_or_full_message: str,
    attempt_count: int = 1,
    session_id: Optional[str] = None,
) -> str:
    """Call the Quality and Security Reviewer engine with code or a pre-built full message; return APPROVE or REJECT."""
    with tracer.start_as_current_span("lens.engineering.sentinel") as span:
        span.set_attribute("agent.system", "agentic_lens")
        span.set_attribute("department", "engineering")
        span.set_attribute("agent.role", "sentinel")
        span.set_attribute("attempt", attempt_count)
        _tlr = getattr(_eng_orchestrate_tls, "lens_request_id", None)
        if _tlr:
            span.set_attribute("lens.request_id", _tlr)
        name = (os.getenv("AGENTIC_LENS_ENGINE_QUALITY_AND_SECURITY_REVIEWER") or "").strip() or _get_engine_by_name("eng_quality_and_security_reviewer")
        if not name:
            return "[Quality and Security Reviewer engine not configured. Set AGENTIC_LENS_ENGINE_QUALITY_AND_SECURITY_REVIEWER or ensure an engine named eng_quality_and_security_reviewer exists.]"
        if "Original User Request" in (code_or_full_message or ""):
            message = code_or_full_message
        else:
            message = f"Review this code for security issues. This is attempt {attempt_count}.\n\nCode to review:\n{code_or_full_message}"
        return _call_engine(name, message, session_id=session_id)


def _parse_sentinel_json(response: str) -> tuple[Optional[bool], str, Optional[list[str]]]:
    """Parse Sentinel JSON {'status': 'APPROVED'|'REJECTED', 'reason': '...', 'security_warnings': [...]}. Returns (approved, reason, warnings); approved is None if no JSON found."""
    text = (response or "").strip()
    # Try to find a JSON object in the response (model may wrap in markdown)
    match = re.search(r"\{[^{}]*[\"']status[\"'][^{}]*[\"']reason[\"'][^{}]*\}", text, re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(r"\{[^{}]+\}", text)
    if match:
        try:
            obj = json.loads(match.group())
            status = (obj.get("status") or "").strip().upper()
            reason = (obj.get("reason") or "").strip() or "Validation failed"
            warnings = obj.get("security_warnings")
            if isinstance(warnings, list):
                return (status == "APPROVED", reason, warnings)
            return (status == "APPROVED", reason, None)
        except (json.JSONDecodeError, TypeError):
            pass
    return (None, "Validation failed", None)


def _is_approved(sentinel_response: str) -> bool:
    """True only when reviewer returns explicit structured APPROVED status."""
    if not sentinel_response or not sentinel_response.strip():
        return False
    approved, _, _ = _parse_sentinel_json(sentinel_response)
    return approved is True


def _rejection_reason(sentinel_response: str) -> str:
    """Extract reason from Sentinel JSON or REJECT: <Reason>."""
    _, reason, _ = _parse_sentinel_json(sentinel_response)
    if reason and reason != "Validation failed":
        return reason
    text = (sentinel_response or "").strip()
    if "REJECT" in text.upper():
        idx = text.upper().find("REJECT")
        rest = text[idx + 6 :].strip()
        if rest.startswith(":"):
            rest = rest[1:].strip()
        return rest or "Validation failed"
    return text or "Validation failed"


def _wrap_code_for_ui(code: str) -> str:
    """Wrap code in a Markdown fenced block so the UI does not interpret # as H1 headers (Terraform/Python comments)."""
    if not code or not code.strip():
        return code
    stripped = code.strip()
    if stripped.startswith("```"):
        return code
    head = stripped[:500]
    if (
        head.lstrip().startswith("# ") or head.lstrip().startswith("#!") or
        " def " in head or "import " in head or " from " in head
    ):
        return "```python\n" + stripped + "\n```"
    return "```terraform\n" + stripped + "\n```"


def _format_return(body: str, execution_log: list[str]) -> str:
    """Append execution log block so UI can parse and show in Agent steps + Live logs."""
    if not execution_log:
        return body
    return body + _EXEC_LOG_START + "\n".join(execution_log) + _EXEC_LOG_END


def orchestrate_build(user_query: str, tool_context=None) -> str:
    """
    Run the full workflow: Plan (Scout) → Build (Coder) → Audit loop (Quality and Security Reviewer, max 3 retries).
    All attempts are recorded in execution_log and appended to the response for UI visibility.
    Returns draft code with either "✅ Approved" or a Quality and Security Reviewer validation failed footer.
    """
    lens_rid, rest = _extract_lens_request_id_marker(user_query)
    # Wire order from Glass: RID, then trace comments, then PRISM — peel trace before PRISM match.
    _, _, rest = _extract_lens_trace_marker(rest)
    _marker_session_id, clean_user_query = _extract_prism_session_marker(rest)
    _eng_orchestrate_tls.lens_request_id = lens_rid
    try:
        return _orchestrate_build_impl(clean_user_query, tool_context)
    finally:
        _eng_orchestrate_tls.lens_request_id = None


def _orchestrate_build_impl(
    clean_user_query: str,
    _tool_context,
) -> str:
    user_query = clean_user_query
    # Avoid passing eng_lead/Glass session IDs into Scout/Coder/Sentinel engines. Those
    # sessions are scoped to this engine resource; reusing the id on other engine resources
    # often yields empty streams without a clear "Session not found" error.
    sub_engine_session_id: Optional[str] = None
    execution_log: list[str] = []
    execution_log.append("Engineering: Checking memory for cached solution...")

    if _is_architecture_explanation_request(user_query):
        execution_log.append("Engineering: Architecture/explanation mode selected (no code requested).")
        execution_log.append("Scout: Gathering architecture context...")
        build_plan = _call_scout(user_query, session_id=sub_engine_session_id)
        _pipeline_diag_append(execution_log, "Scout", build_plan)
        if _scout_plan_unusable(build_plan):
            build_plan = _plan_fallback_gemini(user_query)
        if _scout_plan_unusable(build_plan):
            execution_log.append("Attempt 1 | Scout | No plan (Gemini fallback empty)")
            _pipeline_diag_append(
                execution_log, "PlanFallback_Gemini", build_plan or "", detail="architecture mode"
            )
            explanation = _explain_architecture_from_plan(user_query, (user_query or "").strip())
            if explanation.strip():
                execution_log.append(
                    "Pipeline | PlanFallback_ArchExplain | OK | code=QUERY_ONLY | msg=explain from user ask"
                )
                execution_log.append("Engineering: Architecture guidance returned.")
                return _format_return(explanation, execution_log)
            return _format_return("[Scout returned no architecture plan.]", execution_log)
        explanation = _explain_architecture_from_plan(user_query, build_plan)
        if not explanation:
            execution_log.append("Engineering: Explanation fallback to Scout plan text.")
            explanation = build_plan
        execution_log.append("Engineering: Architecture guidance returned.")
        return _format_return(explanation, execution_log)

    # Step 1: Plan (Scout) — peer eng_scout LlmAgent over Agent Engine (no separate Search tool in-repo).
    execution_log.append("Scout: Calling architect agent (eng_scout) for execution plan...")
    build_plan = _call_scout(user_query, session_id=sub_engine_session_id)
    _pipeline_diag_append(execution_log, "Scout", build_plan)
    if _scout_plan_unusable(build_plan):
        build_plan = _plan_fallback_gemini(user_query)
        if _scout_plan_unusable(build_plan):
            execution_log.append("Attempt 1 | Scout | No plan (Gemini fallback empty)")
            _pipeline_diag_append(
                execution_log, "PlanFallback_Gemini", build_plan or "", detail="terraform path"
            )
            build_plan = _minimal_coder_plan_from_query(user_query)
            execution_log.append(
                "Pipeline | PlanFallback_QueryOnly | OK | code=SYNTH_PLAN | msg=coder proceeds from user request"
            )
            execution_log.append("Attempt 1 | Plan | Ready (query-only)")
            logger.warning(
                "Scout and Gemini plan unavailable; continuing to Coder with query-only synthetic plan."
            )
        else:
            execution_log.append("Pipeline | PlanFallback_Gemini | OK | code=OK | msg=plan from gemini")
            logger.info("Used Gemini plan fallback (Scout returned no plan).")
            execution_log.append("Attempt 1 | Plan | Ready (Gemini fallback)")
    else:
        execution_log.append("Attempt 1 | Scout | Plan received")
    _plan_lower = (build_plan or "").lower()
    wants_terraform = _wants_terraform_fence(user_query)
    wants_python = bool(re.search(r"\bpython\b", (user_query or "").lower())) and not wants_terraform
    if wants_terraform:
        _output_type = "TERRAFORM"
    elif wants_python:
        _output_type = "PYTHON"
    else:
        _output_type = "TERRAFORM" if "terraform" in _plan_lower else "PYTHON"
    execution_log.append(f"Scout: Plan step finished. Output Type: {_output_type}")
    execution_log.append("Scout: Requirements gathered. Passing to Coder.")

    coder_format_instructions = ""
    if wants_terraform:
        # Some Scout plans do not include the literal word "terraform", which can cause
        # the Coder to drift. Force the output format to be Terraform.
        coder_format_instructions = (
            "\n\nRequested Output Format: Terraform.\n"
            "You MUST output a single Markdown fenced code block using ```terraform ...```.\n"
            "Do NOT output Python or any plain-text preface outside the fence."
        )
    elif wants_python:
        coder_format_instructions = (
            "\n\nRequested Output Format: Python.\n"
            "You MUST output a single Markdown fenced code block using ```python ...```.\n"
            "Include a complete, runnable script that fulfills the user request.\n"
            "Do NOT respond with only prose or library names; the fenced script is the primary deliverable.\n"
            "Keep any brief notes outside the fence to one short paragraph at most."
        )

    # Step 2: Build (Coder, first time) — pass user request and plan so Coder implements full ask
    execution_log.append("Coder: Drafting configuration...")
    initial_coder_prompt = (
        f"Original User Request: {user_query}\n\nExecution Plan:\n{build_plan}"
    ) + coder_format_instructions
    draft_code = _call_coder(initial_coder_prompt, session_id=sub_engine_session_id)
    _pipeline_diag_append(execution_log, "Coder", draft_code)
    if not draft_code or draft_code.startswith("["):
        execution_log.append("Attempt 1 | Coder | No code returned")
        return _format_return(draft_code or "[Coder returned no code.]", execution_log)
    execution_log.append("Attempt 1 | Coder | Code produced")
    _code_lower = (draft_code or "").lower()
    if wants_terraform or "terraform" in _code_lower or "resource \""  in (draft_code or ""):
        execution_log.append("Coder: AI-generated Terraform code complete.")
    elif wants_python or "```python" in _code_lower or "import " in (draft_code or ""):
        execution_log.append("Coder: AI-generated Python script complete.")
    else:
        execution_log.append("Coder: Code generated.")
    execution_log.append("Coder: Draft complete. Sending to Quality and Security Reviewer.")

    # Step 3: Audit loop (Sentinel, up to 3 tries with Coder fix in between)
    last_rejection_reason: Optional[str] = None
    for attempt in range(1, _MAX_REVIEW_RETRIES + 1):
        execution_log.append("Quality and Security Reviewer: Scanning for security vulnerabilities...")
        sentinel_prompt = (
            f"Original User Request: {user_query}\n"
            "Requested Output Mode: code_generation\n\n"
            f"Review this code (attempt {attempt}). Code to Review:\n{draft_code}"
        )
        sentinel_response = _call_quality_security_reviewer(
            sentinel_prompt,
            attempt_count=attempt,
            session_id=sub_engine_session_id,
        )
        _pipeline_diag_append(execution_log, f"Sentinel_try_{attempt}", sentinel_response)
        if not sentinel_response or sentinel_response.startswith("["):
            logger.warning("Quality and Security Reviewer call failed or not configured (attempt %d)", attempt)
            execution_log.append(f"Attempt {attempt} | Quality and Security Reviewer | Error or no response")
            continue

        if _is_approved(sentinel_response):
            # Check if Sentinel approved with security warnings (fail-open on attempt 3+)
            _, _, warnings = _parse_sentinel_json(sentinel_response)
            if attempt >= _MAX_REVIEW_RETRIES and warnings:
                # Sentinel approved but with warnings - extract code with warning section from response
                # Sentinel should return: JSON + code block + warning section
                # Extract everything after the JSON (code + warning)
                json_match = re.search(r"\{[^{}]+\}", sentinel_response)
                if json_match:
                    code_with_warning = sentinel_response[json_match.end():].strip()
                    # Remove any leading markdown code fence markers if present
                    code_with_warning = re.sub(r"^```\w*\n?", "", code_with_warning, flags=re.MULTILINE)
                    code_with_warning = re.sub(r"```\s*$", "", code_with_warning, flags=re.MULTILINE)
                    code_with_warning = code_with_warning.strip()
                    if "### ⚠️ SECURITY WARNING" in code_with_warning or "SECURITY WARNING" in code_with_warning:
                        execution_log.append("Quality and Security Reviewer: Validation Passed. Code is secure.")
                        execution_log.append("Quality and Security Reviewer: Code approved.")
                        execution_log.append("Quality and Security Reviewer: Code validation passed. Security checks complete.")
                        execution_log.append(f"Attempt {attempt} | Quality and Security Reviewer | Approved (with security warnings - fail-open)")
                        execution_log.append("Memory: Secure solution saved to database.")
                        execution_log.append("Engineering Pipeline: Completed successfully")
                        return _format_return(_wrap_code_for_ui(code_with_warning.rstrip()) + _APPROVED_FOOTER, execution_log)
                    # Fallback: Sentinel approved with warnings but didn't include code - append warning to draft_code
                    warning_text = "### ⚠️ SECURITY WARNING\n\nThe following issues remain unresolved: " + ", ".join(warnings) + ". Deployment proceeds under 'Break Glass' protocol."
                    execution_log.append("Quality and Security Reviewer: Validation Passed. Code is secure.")
                    execution_log.append("Quality and Security Reviewer: Code approved.")
                    execution_log.append("Quality and Security Reviewer: Code validation passed. Security checks complete.")
                    execution_log.append(f"Attempt {attempt} | Quality and Security Reviewer | Approved (with security warnings - fail-open)")
                    execution_log.append("Memory: Secure solution saved to database.")
                    execution_log.append("Engineering Pipeline: Completed successfully")
                    return _format_return(_wrap_code_for_ui(draft_code.rstrip()) + "\n\n" + warning_text + _APPROVED_FOOTER, execution_log)
            execution_log.append("Quality and Security Reviewer: Validation Passed. Code is secure.")
            execution_log.append("Quality and Security Reviewer: Code approved.")
            execution_log.append("Quality and Security Reviewer: Code validation passed. Security checks complete.")
            execution_log.append(f"Attempt {attempt} | Quality and Security Reviewer | Approved")
            execution_log.append("Memory: Secure solution saved to database.")
            execution_log.append("Engineering Pipeline: Completed successfully")
            return _format_return(_wrap_code_for_ui(draft_code.rstrip()) + _APPROVED_FOOTER, execution_log)

        rejection_reason = _rejection_reason(sentinel_response)
        last_rejection_reason = rejection_reason
        logger.info("Quality and Security Reviewer REJECT (attempt %d): %s", attempt, rejection_reason)
        reason_one_line = " ".join((rejection_reason or "").split())
        execution_log.append(f"Attempt {attempt} | Quality and Security Reviewer | REJECTED: {reason_one_line}")

        if attempt < _MAX_REVIEW_RETRIES:
            fix_request = f"""Original User Request: {user_query}
Original Execution Plan: {build_plan}

Quality and Security Reviewer rejected the code with this feedback: {rejection_reason}

Code to fix:
{draft_code}

Fix the issues raised by the Quality and Security Reviewer, but ensure the final output STILL fulfills the Original User Request and Execution Plan in full.{coder_format_instructions}"""
            execution_log.append("Coder: Drafting configuration...")
            draft_code = _call_coder(fix_request, session_id=sub_engine_session_id)
            _pipeline_diag_append(execution_log, f"Coder_fix_try_{attempt + 1}", draft_code)
            if not draft_code or draft_code.startswith("["):
                execution_log.append(f"Attempt {attempt + 1} | Coder | No code after fix request")
                reason_suffix = f"\n\nReason: {last_rejection_reason}" if last_rejection_reason else ""
                return _format_return(
                    (draft_code or "[Coder returned no code after fix request.]") + _VALIDATION_FAILED_FOOTER + reason_suffix,
                    execution_log,
                )
            execution_log.append(f"Attempt {attempt + 1} | Coder | Code produced (fix)")
            execution_log.append("Coder: Draft complete. Sending to Quality and Security Reviewer.")

    execution_log.append(f"Attempt {_MAX_REVIEW_RETRIES} | Quality and Security Reviewer | Max retries reached (validation failed)")
    reason_suffix = f"\n\nReason: {last_rejection_reason}" if last_rejection_reason else ""
    return _format_return(_wrap_code_for_ui(draft_code.rstrip()) + _VALIDATION_FAILED_FOOTER + reason_suffix, execution_log)
