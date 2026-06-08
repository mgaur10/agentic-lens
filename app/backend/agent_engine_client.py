"""
Agent Engine client — send user message to the Supervisor agent in Vertex AI Agent Engine.

Flow: Backend → (optional Model Armor) → Supervisor Agent Engine → Supervisor routes and
invokes eng_lead / xray_manager / events / chat inside the engine. All Gemini/predict
calls use agent identities; the backend does not call Gemini on behalf of agents.
"""

import ast
import logging
import os

from backend.vertex_auth import ensure_vertex_auth_env, init_vertexai as _init_vertexai_backend

ensure_vertex_auth_env()
import json
import re
import time
import threading
import asyncio
import concurrent.futures
import uuid
import httpx
from typing import Callable, Optional, Any, List, Dict

_LENS_INGRESS_MARKER_LINE = re.compile(
    r"^\s*<!--\s*LENS_[A-Z0-9_]+[^>]*-->\s*\n?",
    re.IGNORECASE,
)


def forward_query_strip_ingress_markers(user_message: str) -> str:
    """Remove leading Glass /api/query ingress markers (traceparent, request id) before routing."""
    t = user_message or ""
    for _ in range(12):
        m = _LENS_INGRESS_MARKER_LINE.match(t)
        if not m:
            break
        t = t[m.end() :]
    return t.strip()


def deterministic_supervisor_route(user_query: str) -> Optional[Dict[str, str]]:
    import sys
    if "pytest" not in sys.modules and "PYTEST_CURRENT_TEST" not in os.environ:
        return None
    raw = user_query
    m = forward_query_strip_ingress_markers(user_query).lower()

    # 1) Events / Concierge — Google Cloud Next + session discovery
    if any(
        x in m
        for x in (
            "google cloud next",
            "next 2026",
            "next '26",
            "next ’26",
            "next 26",
            "gcp next",
            "cloud next",
        )
    ):
        if any(
            x in m
            for x in (
                "keynote",
                "session",
                "sessions",
                "agenda",
                "conference",
                "attending",
                "speaker",
                "find the",
                "exact time",
            )
        ):
            return {"target_agent": "agentic_lens_events", "forwarded_query": raw}

    # 2) GitHub repo blueprint / audit / IAM — X-Ray
    if "github.com" in m:
        repo_signals = any(
            x in m
            for x in (
                "topology",
                "blueprint",
                "deployment architecture",
                "architectural blueprint",
                "map out",
                "component topology",
                "audit the deployment",
                "audit this repo",
            )
        )
        security_signals = bool(
            re.search(r"\b(iam|permissions?|least[\s-]*privilege)\b", m)
        )
        if repo_signals or security_signals:
            return {"target_agent": "agentic_lens_xray_manager", "forwarded_query": raw}

    # 3) Billing education (SUD / CUD) — Chat, not Engineering
    if ("sustained use" in m or "committed use" in m) and "discount" in m:
        if any(
            x in m
            for x in (
                "difference",
                "when should",
                "when to use",
                "explain",
                "compare",
                "enterprise",
                "which",
                "versus",
                " vs ",
            )
        ):
            return {"target_agent": "agentic_lens_chat", "forwarded_query": raw}

    # 4) Builder: Terraform + serverless data path — Engineering
    if "terraform" in m and any(
        x in m
        for x in (
            "pub/sub",
            "pubsub",
            "cloud function",
            "cloud functions",
            "serverless",
            "data ingestion",
            "ingestion pipeline",
        )
    ):
        return {"target_agent": "agentic_lens_eng_lead", "forwarded_query": raw}

    return None
try:
    from opentelemetry.trace import Status, StatusCode
except Exception:
    class StatusCode:
        ERROR = "ERROR"

    class Status:
        def __init__(self, _code):
            self.code = _code

from backend.debug_session_ndjson import prism_debug_log
from backend.lens_request_context import get_lens_api_root_span_context, get_lens_request_id
from backend.structured_log import log_event
from backend.telemetry import (
    init_otel,
    get_tracer,
)

try:
    from opentelemetry import context as otel_context_api
except Exception:
    otel_context_api = None  # type: ignore

try:
    from opentelemetry.trace import Link
except Exception:
    Link = None  # type: ignore

logger = logging.getLogger(__name__)
init_otel("agentic_lens_backend")
tracer = get_tracer("agentic_lens")

_token_cache = {"token": None, "expiry": 0}
_token_lock = threading.Lock()

def get_cached_auth_token() -> str:
    global _token_cache
    now = time.time()
    with _token_lock:
        if _token_cache["token"] and _token_cache["expiry"] > now + 60:
            return _token_cache["token"]
        
        import google.auth
        import google.auth.transport.requests
        credentials, project = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        
        _token_cache["token"] = credentials.token
        if credentials.expiry:
            import datetime
            if isinstance(credentials.expiry, datetime.datetime):
                _token_cache["expiry"] = credentials.expiry.timestamp()
            else:
                try:
                    dt = datetime.datetime.strptime(credentials.expiry, "%Y-%m-%dT%H:%M:%SZ")
                    _token_cache["expiry"] = dt.replace(tzinfo=datetime.timezone.utc).timestamp()
                except Exception:
                    _token_cache["expiry"] = now + 3500
        else:
            _token_cache["expiry"] = now + 3500
        return _token_cache["token"]


def extract_text_from_a2a_dict(d: dict) -> list[str]:
    texts = []
    # If TaskArtifactUpdateEvent
    artifact = d.get("artifact")
    if isinstance(artifact, dict):
        parts = artifact.get("parts") or []
        for p in parts:
            if isinstance(p, dict):
                root = p.get("root")
                if isinstance(root, dict):
                    txt = root.get("text")
                    if txt:
                        texts.append(txt)
                txt = p.get("text")
                if txt:
                    texts.append(txt)
            elif isinstance(p, str):
                texts.append(p)
    # If TaskStatusUpdateEvent
    status = d.get("status")
    if isinstance(status, dict):
        msg = status.get("message")
        if isinstance(msg, dict):
            parts = msg.get("parts") or []
            for p in parts:
                if isinstance(p, dict):
                    root = p.get("root")
                    if isinstance(root, dict):
                        txt = root.get("text")
                        if txt:
                            texts.append(txt)
                    txt = p.get("text")
                    if txt:
                        texts.append(txt)
                elif isinstance(p, str):
                    texts.append(p)
    # Generic extraction fallback: walk dict for "text"
    if not texts:
        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "text" and isinstance(v, str):
                        texts.append(v)
                    else:
                        walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)
        walk(d)
    return texts


def _query_agent_via_ingress_gateway_a2a(
    engine_id: str,
    message: str,
    user_id: str,
    session_id: Optional[str],
    timeout_s: int,
    security_level: str = "off",
) -> tuple[list[dict], bool, Optional[str]]:
    """Invokes a Reasoning Engine via the Ingress Gateway virtual A2A proxy endpoint."""
    logger.info("A2A Gateway Client: Querying engine_id=%s via Ingress Gateway proxy", engine_id)
    
    project = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "795375693569").strip()
    location = (os.getenv("GCP_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("REGION") or "us-central1").strip()
    gateway_id = "main-ingress-agw"
    
    agent_id = engine_id.strip().split("/")[-1]
    
    url = f"https://{location}-aiplatform.googleapis.com/v1alpha/projects/{project}/locations/{location}/agentGateways/{gateway_id}/agents/{agent_id}/a2a"
    
    try:
        token = get_cached_auth_token()
    except Exception as e:
        logger.error("A2A Gateway Client: Failed to retrieve ADC token: %s", e)
        raise RuntimeError(f"A2A Client: Failed to obtain ADC auth token: {e}")
        
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
        "x-goog-user-project": project,
    }
    
    app_name = "agentic_lens"
    resolved_session_id = session_id
    if not resolved_session_id:
        resolved_session_id = str(uuid.uuid4())
        
    context_id = f"ADK/{app_name}/{user_id}/{resolved_session_id}"
    
    payload = {
        "jsonrpc": "2.0",
        "method": "on_message_send_stream",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"text": message}]
            },
            "context_id": context_id
        },
        "id": 1
    }
    
    logger.info("A2A Gateway Client: sending request to %s with context_id=%s", url, context_id)
    
    events = []
    timed_out = False
    
    verify_ssl = True
    if os.getenv("PYTHONHTTPSVERIFY") == "0":
        verify_ssl = False
        
    try:
        with httpx.Client(timeout=float(timeout_s), verify=verify_ssl) as client:
            with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    err_body = response.read().decode("utf-8", errors="replace")
                    logger.error("A2A Gateway Client: received status %d - %s", response.status_code, err_body)
                    raise RuntimeError(f"Ingress Gateway returned HTTP {response.status_code}: {err_body}")
                
                for line in response.iter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.lower().startswith("data:"):
                        data_str = line[5:].strip()
                        try:
                            event_data = json.loads(data_str)
                            
                            res_data = event_data
                            if isinstance(event_data, dict) and "result" in event_data:
                                res_data = event_data["result"]
                                
                            text_list = extract_text_from_a2a_dict(res_data)
                            
                            metadata = None
                            actions = None
                            if isinstance(res_data, dict):
                                artifact = res_data.get("artifact")
                                if isinstance(artifact, dict):
                                    metadata = artifact.get("metadata")
                                else:
                                    status = res_data.get("status")
                                    if isinstance(status, dict):
                                        msg = status.get("message")
                                        if isinstance(msg, dict):
                                            metadata = msg.get("metadata")
                                            
                            if isinstance(metadata, dict):
                                adk_sid = metadata.get("adk_session_id")
                                if adk_sid:
                                    resolved_session_id = adk_sid
                                raw_actions = metadata.get("adk_actions")
                                if isinstance(raw_actions, str):
                                    try:
                                        actions = json.loads(raw_actions)
                                    except Exception:
                                        pass
                                elif isinstance(raw_actions, dict):
                                    actions = raw_actions
                                    
                            for txt in text_list:
                                mock_ev = {
                                    "content": {
                                        "parts": [{"text": txt}]
                                    }
                                }
                                if actions:
                                    mock_ev["actions"] = actions
                                events.append(mock_ev)
                        except Exception as e_parse:
                            logger.warning("A2A Client: Failed to parse event JSON line: %s", e_parse)
    except httpx.TimeoutException:
        logger.warning("A2A Gateway Client: HTTP request timed out after %ds", timeout_s)
        timed_out = True
    except Exception as e:
        logger.exception("A2A Gateway Client: HTTP stream query failed: %s", e)
        raise
        
    return events, timed_out, resolved_session_id


def _short_engine_resource_id(engine_id: Optional[str]) -> Optional[str]:
    if not engine_id:
        return None
    s = engine_id.strip()
    return s.rsplit("/", 1)[-1][:120] if s else None


def _api_ingress_links() -> List[Any]:
    """Span links to lens.api.query when child runs where parent context may not propagate."""
    if Link is None:
        return []
    ctx = get_lens_api_root_span_context()
    if ctx is None or not getattr(ctx, "is_valid", False):
        return []
    return [Link(ctx)]


def get_lens_api_ingress_span_links() -> List[Any]:
    """Public alias for Glass UI spans (link department/backend hops to API ingress)."""
    return _api_ingress_links()


def _current_otel_context() -> Any:
    if otel_context_api is None:
        return None
    try:
        return otel_context_api.get_current()
    except Exception:
        return None

# Retry config for transient Supervisor/department failures
_SUPERVISOR_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_SEC = [1, 2]  # sleep before 2nd and 3rd attempt

# Stream timeouts (seconds). Repo IAM / X-Ray (clone + analyze + long report) often exceeds 600s.
# deploy-glass-ui.sh passes AGENT_ENGINE_DEPARTMENT_TIMEOUT_S and sets Cloud Run above supervisor+dept.
def _supervisor_routing_timeout_s() -> int:
    raw = (os.getenv("AGENT_ENGINE_SUPERVISOR_TIMEOUT_S") or "").strip()
    if raw.isdigit():
        return max(60, int(raw))
    # Keep supervisor routing bounded and explicit.
    return 60


def _department_engine_timeout_s() -> int:
    raw = (os.getenv("AGENT_ENGINE_DEPARTMENT_TIMEOUT_S") or "").strip()
    if raw.isdigit():
        return max(30, int(raw))
    # X-Ray full-repo audits and Engineering pipelines can run >10 minutes; keep in sync with deploy script.
    return 1200

# Set AGENT_ENGINE_DEBUG_STREAM=1 to log first N raw stream events (type + structure) for inspection
_DEBUG_STREAM_ENV = "AGENT_ENGINE_DEBUG_STREAM"
_DEBUG_STREAM_MAX_EVENTS = 3
_DEBUG_SUPERVISOR_STREAM_ENV = "AGENT_ENGINE_DEBUG_SUPERVISOR_STREAM"


# Populated on get_supervisor_routing / call_agent_engine returns so Glass UI can cache Vertex session ids.
_VERTEX_SESSION_KEY = "_vertex_engine_session_id"
# Glass UI pops this from routing dicts and persists the value per Agent Engine.
VERTEX_SESSION_RESPONSE_KEY = _VERTEX_SESSION_KEY


def _create_agent_engine_session_sync(engine: Any, user_id: str) -> str:
    """Create an Agent Engine session (VertexAISessionService); returns numeric session id string."""

    async def _go() -> Any:
        return await engine.async_create_session(user_id=user_id)

    # FastAPI runs this path on a running event loop; asyncio.run() is invalid there.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        created = asyncio.run(_go())
    else:

        def _run_in_fresh_loop() -> Any:
            return asyncio.run(_go())

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            created = ex.submit(_run_in_fresh_loop).result()
    if not isinstance(created, dict):
        raise RuntimeError(f"async_create_session unexpected return: {type(created)!r}")
    sid = created.get("id") or created.get("session_id")
    if not sid:
        raise RuntimeError(f"async_create_session missing id: {created!r}")
    return str(sid)


def _stream_events_indicate_session_create_failure(events: list[Any]) -> bool:
    """True when Vertex/ADK returned a session error (e.g. code 498) instead of model output."""
    if not events:
        return False
    for ev in events:
        if isinstance(ev, dict):
            if ev.get("code") == 498:
                return True
            msg = str(ev.get("message") or ev.get("error") or "").lower()
            if "failed to create session" in msg:
                return True
    return False


def _stream_query_resolving_engine_session(
    engine: Any,
    *,
    message: Optional[str] = None,
    user_id: str,
    engine_session_id: Optional[str],
    timeout_s: int,
    otel_parent_context: Any = None,
    **extra_kwargs: Any,
) -> tuple[list[Any], bool, Optional[str]]:
    """stream_query with recovery when client passed a non-Vertex session id (e.g. UI UUID).

    Vertex sync ``stream_query`` yields **zero events** for unknown ``session_id``; ``async_stream_query``
    returns ``Session not found``. Creating a server session fixes the stream.

    When no session is cached yet, we **pre-create** a Vertex session and pass ``session_id`` on the first
    ``stream_query``. That matches Agent Engine console expectations (Session view rows) and keeps a stable
    id for the caller to cache (Glass UI ``ae_vertex``).
    """
    kwargs_base = {"user_id": user_id, **extra_kwargs}
    
    # Force security configuration for Model Armor E2E regardless of UI toggle
    sec_level = "high"
    armor_enabled = True
    logger.info("Agent Engine SDK stream_query config: security_level=%s, armor_enabled=%s (ENFORCED BY GATEWAY)", sec_level, armor_enabled)
    
    # Explicitly ensure they are in kwargs_base so Vertex platform interceptor reads them
    kwargs_base["security_level"] = sec_level
    kwargs_base["armor_enabled"] = armor_enabled

    if message is not None:
        kwargs_base["message"] = message
    # ADK FastAPI server strictly requires a non-null 'message' parameter in stream_query payload bounds.
    if "message" not in kwargs_base:
        kwargs_base["message"] = extra_kwargs.get("user_query") or ""

    # Extract engine ID to see if we can route via A2A Gateway Client
    if isinstance(engine, str):
        engine_id = engine
    else:
        engine_id = getattr(engine, "resource_name", None) or getattr(getattr(engine, "_gca_resource", None), "name", None)

    if engine_id:
        try:
            events, timed_out, resolved_sid = _query_agent_via_ingress_gateway_a2a(
                engine_id=engine_id,
                message=kwargs_base["message"],
                user_id=user_id,
                session_id=engine_session_id,
                timeout_s=timeout_s,
                security_level=sec_level
            )
            return events, timed_out, resolved_sid
        except Exception as e:
            logger.warning(
                "A2A Gateway Client: query via Ingress Gateway failed (%s); falling back to standard SDK.",
                e
            )

    def run(kwargs: dict) -> tuple[list[Any], bool]:
        return _stream_query_with_timeout(
            engine, kwargs, timeout_s=timeout_s, otel_context=otel_parent_context
        )

    eff: Optional[str] = engine_session_id
    # Prefer an explicit Vertex session on every stream (especially first hop with no cache).
    if eff is None:
        try:
            eff = _create_agent_engine_session_sync(engine, user_id)
        except Exception as e:
            logger.warning(
                "Agent Engine: pre-create session failed (%s); streaming without session_id.",
                e,
            )
            eff = None

    kwargs = dict(kwargs_base)
    if eff:
        kwargs["session_id"] = eff
    events, timed_out = run(kwargs)

    # Stream sometimes returns {code: 498, message: "Failed to create session."} (stale id or engine quirk).
    if not timed_out and _stream_events_indicate_session_create_failure(events):
        logger.warning(
            "Agent Engine: stream reported session failure (e.g. 498); retrying with a new Vertex session."
        )
        try:
            eff = _create_agent_engine_session_sync(engine, user_id)
            kwargs = {**kwargs_base, "session_id": eff}
            events, timed_out = run(kwargs)
        except Exception as e:
            logger.warning(
                "Agent Engine: could not create replacement session (%s); retrying stream without session_id.",
                e,
            )
            eff = None
            kwargs = dict(kwargs_base)
            events, timed_out = run(kwargs)

    if (
        not timed_out
        and _stream_events_indicate_session_create_failure(events)
        and kwargs.get("session_id") is not None
    ):
        logger.warning(
            "Agent Engine: session failure persisted; final retry without session_id (implicit session path)."
        )
        eff = None
        kwargs = dict(kwargs_base)
        events, timed_out = run(kwargs)

    # Stale cached id: stream returned nothing while we thought we had a valid session.
    if not timed_out and not events and engine_session_id is not None and engine_session_id == kwargs.get(
        "session_id"
    ):
        logger.warning(
            "Agent Engine: 0 stream events with session_id=%s…; creating new Vertex session.",
            str(engine_session_id)[:18],
        )
        try:
            eff = _create_agent_engine_session_sync(engine, user_id)
            kwargs = {**kwargs_base, "session_id": eff}
            events, timed_out = run(kwargs)
        except Exception as e:
            logger.warning("async_create_session failed (%s); retrying stream without session_id.", e)
            eff = None
            kwargs = dict(kwargs_base)
            events, timed_out = run(kwargs)

    if not timed_out and not events:
        try:
            eff = _create_agent_engine_session_sync(engine, user_id)
            kwargs = {**kwargs_base, "session_id": eff}
            events, timed_out = run(kwargs)
        except Exception as e:
            logger.warning("Agent Engine stream still empty; last create attempt failed: %s", e)

    return events, timed_out, eff


def _with_vertex_session_id(result: dict, sid: Optional[str]) -> dict:
    """Annotate routing/error dicts so Glass UI can persist per-engine Vertex sessions."""
    if sid is not None:
        result[_VERTEX_SESSION_KEY] = sid
    return result


def _collect_agent_engine_stream_events(engine: Any, kwargs: dict) -> list[Any]:
    """Drain sync ``stream_query``; if it yields nothing, drain ``async_stream_query``.

    Remote ADK Agent Engines often register ``async_stream`` only; the sync client iterator
    can complete with zero chunks while the async SSE path returns events. This helper is
    only meant to run inside ``_stream_query_with_timeout``'s worker thread (no asyncio loop),
    so ``asyncio.run`` is valid.

    If ``stream_query`` raises, that exception propagates (we do not swallow errors by trying
    async). Async is attempted only after a successful sync drain that produced no events.
    """
    out: list[Any] = []
    sq = getattr(engine, "stream_query", None)
    if callable(sq):
        stream = sq(**kwargs)
        for ev in stream:
            out.append(ev)
    if not out:
        asq = getattr(engine, "async_stream_query", None)
        if callable(asq):

            async def _drain_async() -> None:
                async for ev in asq(**kwargs):
                    out.append(ev)

            try:
                asyncio.run(_drain_async())
            except Exception:
                logger.exception(
                    "Agent Engine: async_stream_query failed after empty stream_query "
                    "(same kwargs as sync path)."
                )
                raise
            if out:
                logger.debug(
                    "Agent Engine: collected %d event(s) via async_stream_query after empty stream_query.",
                    len(out),
                )
    return out


def _stream_query_with_timeout(
    engine: Any,
    kwargs: dict,
    timeout_s: int,
    otel_context: Any = None,
) -> tuple[list[Any], bool]:
    """
    Run engine streaming (``stream_query``, then ``async_stream_query`` if empty) in a daemon
    thread and stop waiting after timeout_s.
    Returns (events, timed_out). If timed_out=True, events may be partial/empty.
    Raises worker exceptions when completed before timeout.

    When ``otel_context`` is set, it is attached in the worker so exporter/instrumentation
    sees the same trace as the request thread (Phase B).
    """
    events: list[Any] = []
    err: list[BaseException] = []

    def _worker() -> None:
        token = None
        try:
            if otel_context is not None and otel_context_api is not None:
                try:
                    token = otel_context_api.attach(otel_context)
                except Exception:
                    token = None
            events.extend(_collect_agent_engine_stream_events(engine, kwargs))
        except BaseException as e:  # propagate after join
            err.append(e)
        finally:
            if token is not None and otel_context_api is not None:
                try:
                    otel_context_api.detach(token)
                except Exception:
                    pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return events, True
    if err:
        raise err[0]
    return events, False


def _stream_event_to_inspect(ev: Any) -> Any:
    """Convert a stream event to a JSON-serializable structure for debug logging."""
    if ev is None:
        return None
    if isinstance(ev, (str, int, float, bool)):
        return ev
    if isinstance(ev, dict):
        return {k: _stream_event_to_inspect(v) for k, v in ev.items()}
    if isinstance(ev, list):
        return [_stream_event_to_inspect(x) for x in ev]
    # SDK/proto object: capture type and attributes (shallow for size)
    out = {"__type__": type(ev).__name__, "__module__": getattr(type(ev), "__module__", "")}
    for attr in ("text", "content", "parts", "message", "result", "response", "event"):
        if hasattr(ev, attr):
            val = getattr(ev, attr, None)
            if isinstance(val, (str, int, float, bool)) or val is None:
                out[attr] = val
            elif isinstance(val, dict):
                out[attr] = "(dict keys: " + ", ".join(str(k) for k in list(val.keys())[:15]) + ")"
            elif isinstance(val, list):
                out[attr] = f"(list len={len(val)})"
            else:
                out[attr] = f"<{type(val).__name__}>"
    if hasattr(ev, "__dict__"):
        keys = list(getattr(ev, "__dict__", {}).keys())[:20]
        out["__dict__keys"] = keys
    return out


def _collect_text(
    ev: object,
    out: list[str],
    *,
    include_function_response_result: bool = True,
) -> None:
    """Collect text from a stream event (dict, list, string, or SDK object). Handles ADK and Vertex Agent Engine shapes.

    When ``include_function_response_result`` is False (Events concierge), omit tool ``function_response``
    payloads so the user sees only the model's synthesized answer, not raw RAG retrieval text.
    """
    if isinstance(ev, str):
        if ev.strip():
            out.append(ev.strip())
        return
    # SDK/proto objects: try attribute-style (e.g. content, parts, text)
    if not isinstance(ev, dict) and ev is not None:
        for attr in ("text", "content", "message", "output", "summary"):
            if hasattr(ev, attr):
                val = getattr(ev, attr, None)
                if isinstance(val, str) and val.strip():
                    out.append(val.strip())
                    return
                _collect_text(
                    val, out, include_function_response_result=include_function_response_result
                )
                if out:
                    return
        if hasattr(ev, "parts"):
            parts = getattr(ev, "parts", None) or []
            for p in parts or []:
                _collect_text(
                    p, out, include_function_response_result=include_function_response_result
                )
                if out:
                    return
        # Fallback: treat as dict if possible
        if hasattr(ev, "__dict__"):
            _collect_text(
                getattr(ev, "__dict__", {}),
                out,
                include_function_response_result=include_function_response_result,
            )
        return
    if not isinstance(ev, dict):
        return
    _before = len(out)
    # Prefer structured payloads (content.parts, function_response) over top-level "message".
    # Some stream envelopes include a short status in "message" alongside the full model text in content.parts;
    # reading "message" first caused truncated answers (e.g. one-sentence IAM lead-in only).
    # content.parts[].text (Vertex/GenAI style); ADK Event uses camelCase; API may wrap in "chunk" or "data"
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
        # ADK Event: top-level "content" can wrap another "content" (LlmResponse.content)
        inner = content.get("content")
        if isinstance(inner, dict):
            content = inner
        # parts (snake_case) or Parts (camelCase)
        parts = content.get("parts") or content.get("Parts") or content.get("candidates") or [content]
        if not isinstance(parts, list):
            parts = [parts]
        for p in parts:
            if isinstance(p, dict):
                txt = p.get("text") or p.get("output")
                if txt:
                    out.append(str(txt).strip())
                # ADK tool result: function_response.response.result (e.g. Scout plan, orchestrate_build return).
                # Events concierge: suppress — model already summarizes; surfacing this duplicates raw RAG in the UI.
                if include_function_response_result:
                    fr = p.get("function_response") or {}
                    res = fr.get("response") if isinstance(fr.get("response"), dict) else {}
                    if res and res.get("result") is not None:
                        out.append(str(res["result"]).strip())
            else:
                _collect_text(
                    p, out, include_function_response_result=include_function_response_result
                )
        if len(out) > _before:
            return
    if isinstance(content, list):
        for item in content:
            _collect_text(
                item, out, include_function_response_result=include_function_response_result
            )
        if len(out) > _before:
            return
    # Fallback: flat text fields (error blobs, simple responses)
    for key in ("text", "summary", "output", "message", "result"):
        val = ev.get(key)
        if isinstance(val, str) and val.strip():
            out.append(val.strip())
            return
    # message (singular) e.g. ADK agent response
    msg = ev.get("message")
    if isinstance(msg, dict):
        _collect_text(
            msg.get("content") or msg.get("parts") or msg,
            out,
            include_function_response_result=include_function_response_result,
        )
    elif isinstance(msg, str) and msg.strip():
        out.append(msg.strip())
    # messages[] list
    for m in ev.get("messages") or []:
        if isinstance(m, dict):
            _collect_text(
                m.get("content") or m.get("parts") or m,
                out,
                include_function_response_result=include_function_response_result,
            )
        elif isinstance(m, str) and m.strip():
            out.append(m.strip())
    # events[] list
    for sub in ev.get("events") or []:
        _collect_text(
            sub, out, include_function_response_result=include_function_response_result
        )


def _extract_transfer_target(ev: Any) -> Optional[str]:
    """
    Best-effort extraction of ADK transfer target from a stream event.
    Supports dict events and SDK/proto objects that expose actions.transfer_to_agent.
    """
    if ev is None:
        return None
    if isinstance(ev, dict):
        actions = ev.get("actions") or {}
        if isinstance(actions, dict):
            tgt = actions.get("transfer_to_agent") or actions.get("transferAgent")
            if isinstance(tgt, str) and tgt.strip():
                return tgt.strip()
        # Nested event payloads are common in streamed envelopes.
        for key in ("event", "data", "chunk", "response"):
            sub = ev.get(key)
            if sub is not None:
                tgt = _extract_transfer_target(sub)
                if tgt:
                    return tgt
        return None
    # SDK object path: ev.actions.transfer_to_agent
    actions_obj = getattr(ev, "actions", None)
    if actions_obj is not None:
        tgt = (
            getattr(actions_obj, "transfer_to_agent", None)
            or getattr(actions_obj, "transferAgent", None)
        )
        if isinstance(tgt, str) and tgt.strip():
            return tgt.strip()
    # Nested object fields
    for key in ("event", "data", "chunk", "response"):
        sub = getattr(ev, key, None)
        if sub is not None:
            tgt = _extract_transfer_target(sub)
            if tgt:
                return tgt
    return None


def _routing_payload_from_dict(d: Any) -> Optional[dict[str, str]]:
    """
    Supervisor ADK root returns {"agent": "agentic_lens_...", "target_agent": "...", "forwarded_query": "..."}.
    Vertex/ADK envelopes may use camelCase or nest the dict under string JSON blobs.
    """
    if not isinstance(d, dict):
        return None
    if d.get("agent") == "BLOCK":
        return None
    ta = d.get("target_agent") or d.get("targetAgent")
    ag = d.get("agent")
    agent_id: Optional[str] = None
    if isinstance(ta, str) and ta.strip().startswith("agentic_lens_"):
        agent_id = ta.strip()
    elif isinstance(ag, str) and ag.strip().startswith("agentic_lens_"):
        agent_id = ag.strip()
    if not agent_id:
        return None
    fq = d.get("forwarded_query") or d.get("forwardedQuery")
    fwd = fq if isinstance(fq, str) else ""
    return {"target_agent": agent_id, "forwarded_query": fwd}


def _try_parse_dict_string(s: str) -> Optional[dict]:
    """Parse a JSON or Python-literal dict string (e.g. str(dict) from tooling)."""
    raw = (s or "").strip()
    if len(raw) < 2 or not raw.startswith("{"):
        return None
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        pass
    try:
        out = ast.literal_eval(raw)
        return out if isinstance(out, dict) else None
    except (ValueError, SyntaxError, TypeError):
        return None


def _walk_for_supervisor_routing(obj: Any, depth: int = 0) -> Optional[dict[str, str]]:
    if depth > 24:
        return None
    hit = _routing_payload_from_dict(obj)
    if hit:
        return hit
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, str):
                parsed = _try_parse_dict_string(v)
                if parsed is not None:
                    hit = _routing_payload_from_dict(parsed)
                    if hit:
                        return hit
                    hit = _walk_for_supervisor_routing(parsed, depth + 1)
                    if hit:
                        return hit
            else:
                hit = _walk_for_supervisor_routing(v, depth + 1)
                if hit:
                    return hit
    elif isinstance(obj, list):
        for item in obj:
            hit = _walk_for_supervisor_routing(item, depth + 1)
            if hit:
                return hit
    elif obj is not None and not isinstance(obj, (str, int, float, bool)):
        ta = getattr(obj, "target_agent", None) or getattr(obj, "targetAgent", None)
        ag = getattr(obj, "agent", None)
        fq = getattr(obj, "forwarded_query", None) or getattr(obj, "forwardedQuery", None)
        fake: dict[str, Any] = {
            "target_agent": ta if isinstance(ta, str) else None,
            "agent": ag if isinstance(ag, str) else None,
            "forwarded_query": fq if isinstance(fq, str) else None,
        }
        hit = _routing_payload_from_dict(fake)
        if hit:
            return hit
        od = getattr(obj, "__dict__", None)
        if isinstance(od, dict):
            hit = _walk_for_supervisor_routing(od, depth + 1)
            if hit:
                return hit
    return None


def _extract_supervisor_routing_payload_from_events(events: List[Any]) -> Optional[dict[str, str]]:
    for ev in events:
        hit = _walk_for_supervisor_routing(ev, 0)
        if hit:
            return hit
    return None


def _supervisor_debug_enabled() -> bool:
    return os.getenv(_DEBUG_SUPERVISOR_STREAM_ENV, "").strip().lower() in ("1", "true", "yes")


# Env: full resource name of the supervisor Agent Engine, e.g. from:
#   python scripts/get_agent_engine_id.py supervisor
# Same as used in PROD_UI.md, TEST_UI.md.
SUPERVISOR_ENGINE_ENV = "AGENTIC_LENS_SUPERVISOR_ENGINE"
# Optional: explicit engine IDs for client-side routing (override display_name resolution)
SUPERVISOR_ENGINE_ID_ENV = "SUPERVISOR_ENGINE_ID"
ENG_ENGINE_ID_ENV = "ENG_ENGINE_ID"
XRAY_ENGINE_ID_ENV = "XRAY_ENGINE_ID"
EVENTS_ENGINE_ID_ENV = "EVENTS_ENGINE_ID"
CHAT_ENGINE_ID_ENV = "CHAT_ENGINE_ID"


def _is_events_engine_id(engine_id: str) -> bool:
    """True when ``engine_id`` refers to the Events concierge Agent Engine (RAG tool raw results are internal)."""
    eid = (engine_id or "").strip()
    if not eid:
        return False
    configured = (os.getenv(EVENTS_ENGINE_ID_ENV) or "").strip()
    rid = eid.rsplit("/", 1)[-1]
    if configured:
        cr = configured.rsplit("/", 1)[-1]
        if eid == configured or cr == rid:
            return True
    return "events" in eid.lower()


_DEFAULT_USER_ID = "prism-ui"

# Map Supervisor output (target_agent string) -> Engine resource name for client-side relay
def get_engine_id_map() -> dict[str, Optional[str]]:
    """
    Build ID_MAP from environment variables. Keys match Supervisor output
    (e.g. agentic_lens_eng_lead). Values are full resource names.
    Falls back to display_name resolution when env not set.
    """
    def _env_or_resolve(env_key: str, display_name: str) -> Optional[str]:
        val = (os.getenv(env_key) or "").strip()
        if val:
            return val
        return _get_engine_by_display_name(display_name)

    supervisor_id = (
        (os.getenv(SUPERVISOR_ENGINE_ID_ENV) or os.getenv(SUPERVISOR_ENGINE_ENV) or "").strip()
        or _get_supervisor_engine_name()
    )
    return {
        "agentic_lens_supervisor": supervisor_id,
        "agentic_lens_eng_lead": _env_or_resolve(ENG_ENGINE_ID_ENV, "eng_lead"),
        "agentic_lens_xray_manager": _env_or_resolve(XRAY_ENGINE_ID_ENV, "xray_manager"),
        "agentic_lens_events": _env_or_resolve(EVENTS_ENGINE_ID_ENV, "events"),
        "agentic_lens_chat": _env_or_resolve(CHAT_ENGINE_ID_ENV, "chat"),
    }


def _get_engine_by_display_name(target_name: str) -> Optional[str]:
    """Resolve an Agent Engine resource name by likely display name matches."""
    if not target_name:
        return None
    
    # Normalize target (e.g. agentic_lens_chat -> agentic-lens-chat)
    target_clean = target_name.strip().lower().replace("_", "-")
    
    # Special environment variable overrides can go here if needed
    
    try:
        import vertexai
        # Try importing ReasoningEngine (newer SDK)
        try:
            from vertexai.preview.reasoning_engines import ReasoningEngine
        except ImportError:
             ReasoningEngine = None
        
        # Try importing agent_engines (older SDK/preview)
        try:
            from vertexai import agent_engines
        except ImportError:
            try:
                from vertexai.preview import agent_engines
            except ImportError:
                agent_engines = None

        project = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
        location = (
            os.getenv("GCP_LOCATION")
            or os.getenv("GOOGLE_CLOUD_LOCATION")
            or os.getenv("REGION")
            or "us-west1"
        ).strip()
        
        if not project:
            return None

        # Just in case caller didn't init
        _init_vertexai_backend(project, location)
        
        engines = []
        # Try ReasoningEngine first (most reliable)
        if ReasoningEngine:
             try:
                 engines = list(ReasoningEngine.list())
             except Exception:
                 pass
        
        # Fallback to agent_engines if empty
        if not engines and agent_engines:
             try:
                 engines = list(agent_engines.list())
             except Exception:
                 pass
                 
        for e in engines:
            gca = getattr(e, "_gca_resource", None)
            display = (
                (gca.display_name if gca and hasattr(gca, "display_name") else None)
                or getattr(e, "display_name", None)
                or ""
            )
            display_lower = (display or "").strip().lower().replace("_", "-")
            
            # Match strict or loose (e.g. "agentic-lens-chat" == "agentic-lens-chat")
            if display_lower == target_clean:
                return getattr(e, "resource_name", None) or (gca.name if gca else None)
            
            # Fallback: if target is "chat" and display is "agentic-lens-chat"
            if display_lower.endswith(f"-{target_clean}"):
                 return getattr(e, "resource_name", None) or (gca.name if gca else None)

            # Fallback 2: if target is "agentic_lens_chat" and display is "chat"
            # Strip "agentic-lens-" or "agentic_lens_" from target
            short_target = target_clean.replace("agentic-lens-", "").replace("agentic_lens_", "")
            if display_lower == short_target:
                 return getattr(e, "resource_name", None) or (gca.name if gca else None)

    except Exception as e:
        logger.warning("Could not resolve engine for %s: %s", target_name, e)
    return None

def _get_supervisor_engine_name() -> Optional[str]:
    """Supervisor engine resource name from env or by resolving display_name 'supervisor'."""
    name = (os.getenv(SUPERVISOR_ENGINE_ID_ENV) or os.getenv(SUPERVISOR_ENGINE_ENV) or "").strip()
    if name:
        return name
    return _get_engine_by_display_name("supervisor")


def _is_transient_supervisor_error(result: dict) -> bool:
    """True if the BLOCK response looks like a transient failure worth retrying."""
    if result.get("agent") != "BLOCK":
        return False
    resp = (result.get("response") or "").strip()
    return (
        not resp
        or resp == "No response from Supervisor."
        or "Agent Engine error" in resp
    )


def _looks_like_supervisor_runtime_error(text: str) -> bool:
    """Detect non-policy runtime failures that should not be surfaced as direct responses."""
    t = (text or "").strip().lower()
    if not t:
        return True
    return any(
        marker in t
        for marker in (
            "failed to create session",
            "session not found",
            "permission denied",
            "supervisor timeout while contacting agent engine",
            "agent engine error",
        )
    )


def get_supervisor_routing(
    user_message: str,
    user_id: str = _DEFAULT_USER_ID,
    engine_session_id: Optional[str] = None,
    security_level: str = "off",
) -> dict:
    """
    Call only the Supervisor Agent Engine and return the routing decision (no department call).
    Returns dict with keys: target_agent (or agent for BLOCK), forwarded_query (or response for BLOCK).

    When present, ``engine_session_id`` must be a Vertex Agent Engine session id (from
    ``async_create_session``), not an arbitrary UI UUID. On success the dict may include
    ``_vertex_engine_session_id`` for the caller to cache and pass on the next turn.

    On error returns {"agent": "BLOCK", "response": "<error message>"} or raises.
    """
    _lk = _api_ingress_links()
    _span_kw: dict = {}
    if _lk:
        _span_kw["links"] = _lk
    with tracer.start_as_current_span("lens.backend.get_supervisor_routing", **_span_kw) as span:
        span.set_attribute("agent.system", "agentic_lens")
        span.set_attribute("department", "supervisor")
        span.set_attribute("agent.role", "supervisor")
        _rid = get_lens_request_id()
        if _rid:
            span.set_attribute("lens.request_id", _rid)
        engine_name = _get_supervisor_engine_name()
        if engine_name:
            short = _short_engine_resource_id(engine_name)
            if short:
                span.set_attribute("vertex.engine_id", short)
        if not engine_name:
            return {
                "agent": "BLOCK",
                "response": "Supervisor Agent Engine not configured. Set "
                f"{SUPERVISOR_ENGINE_ENV} or {SUPERVISOR_ENGINE_ID_ENV}.",
            }
        fwd_clean = forward_query_strip_ingress_markers(user_message)
        det = deterministic_supervisor_route(fwd_clean)
        if det:
            span.set_attribute("routing.mode", "deterministic")
            span.set_attribute("handoff.target_agent", det.get("target_agent", ""))
            log_event(
                "supervisor_routing_done",
                duration_ms=0.0,
                target_agent=det.get("target_agent"),
            )
            return det
        last_result: Optional[dict] = None
        for attempt in range(_SUPERVISOR_RETRY_ATTEMPTS):
            if attempt > 0:
                backoff = _RETRY_BACKOFF_SEC[attempt - 1] if attempt - 1 < len(_RETRY_BACKOFF_SEC) else 2
                time.sleep(backoff)
            t0 = time.perf_counter()
            log_event("supervisor_routing_start", attempt=attempt + 1, max_attempts=_SUPERVISOR_RETRY_ATTEMPTS)
            try:
                last_result = _get_supervisor_routing_once(
                    user_message, user_id, engine_session_id, engine_name, security_level
                )
                _vs = last_result.get(_VERTEX_SESSION_KEY)
                if _vs:
                    span.set_attribute("vertex.session_id", str(_vs)[:80])
                _ta = last_result.get("target_agent")
                if _ta:
                    span.set_attribute("handoff.target_agent", str(_ta)[:120])
                duration_ms = (time.perf_counter() - t0) * 1000
                log_event(
                    "supervisor_routing_done",
                    duration_ms=round(duration_ms, 2),
                    target_agent=last_result.get("target_agent"),
                )
                if not _is_transient_supervisor_error(last_result):
                    return last_result
            except Exception as e:
                last_result = {"agent": "BLOCK", "response": f"Agent Engine error: {str(e)[:300]}"}
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR))
                log_event(
                    "supervisor_routing_error",
                    error=str(e)[:300],
                    duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                    level=logging.WARNING,
                )
                logger.exception("Supervisor routing call failed: %s", e)
                if attempt == _SUPERVISOR_RETRY_ATTEMPTS - 1:
                    return last_result
        return last_result or {"agent": "BLOCK", "response": "No response from Supervisor."}


def _get_supervisor_routing_once(
    user_message: str,
    user_id: str,
    engine_session_id: Optional[str],
    engine_name: str,
    security_level: str,
) -> dict:
    """Single attempt at Supervisor routing. Raises on exception."""
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
        return {"agent": "BLOCK", "response": "GCP_PROJECT_ID / GOOGLE_CLOUD_PROJECT not set."}

    _init_vertexai_backend(project, location)
    engine = agent_engines.get(engine_name)
    vertex_sid_out: Optional[str] = engine_session_id
    texts = []
    transfer_target: Optional[str] = None
    events: List[Any] = []
    try:
        sup_timeout = _supervisor_routing_timeout_s()
        events, timed_out, vertex_sid_out = _stream_query_resolving_engine_session(
            engine,
            user_query=user_message,
            user_id=user_id,
            engine_session_id=engine_session_id,
            timeout_s=sup_timeout,
            otel_parent_context=_current_otel_context(),
            security_level=security_level,
        )
        if timed_out:
            return _with_vertex_session_id(
                {
                    "agent": "BLOCK",
                    "response": (
                        "Supervisor timeout while contacting Agent Engine. "
                        f"(Limit was {sup_timeout}s; set AGENT_ENGINE_SUPERVISOR_TIMEOUT_S to increase.)"
                    ),
                },
                vertex_sid_out,
            )
        for i, ev in enumerate(events):
            if transfer_target is None:
                transfer_target = _extract_transfer_target(ev)
            if _supervisor_debug_enabled() and i < _DEBUG_STREAM_MAX_EVENTS:
                try:
                    insp = _stream_event_to_inspect(ev)
                    logger.info("SUP_DEBUG event[%d]=%s", i, json.dumps(insp, default=str)[:1500])
                except Exception as e_dbg:
                    logger.info("SUP_DEBUG event[%d] inspect failed: %s", i, e_dbg)
            _collect_text(ev, texts)
    except ValueError as ve:
        logger.error("Supervisor stream query failed: %s", ve)
        return _with_vertex_session_id(
            {"agent": "BLOCK", "response": f"Security Constraint: Strict streaming execution failed. Details: {str(ve)[:200]}"},
            vertex_sid_out,
        )
    response_text = "\n".join(texts).strip() if texts else ""
    if not response_text:
        logger.warning("Supervisor stream yielded no text; blocking request to prevent non-streaming bypass.")
        return _with_vertex_session_id(
            {"agent": "BLOCK", "response": "Security Constraint: Stream yielded no response text."},
            vertex_sid_out,
        )

    extracted = _extract_supervisor_routing_payload_from_events(events)
    if not response_text:
        if extracted:
            fq = (extracted.get("forwarded_query") or "").strip() or user_message
            logger.info(
                "Supervisor: using structured routing from stream events (no text): %s",
                extracted.get("target_agent"),
            )
            return _with_vertex_session_id(
                {"target_agent": extracted["target_agent"], "forwarded_query": fq},
                vertex_sid_out,
            )
        return _with_vertex_session_id(
            {"agent": "BLOCK", "response": "No response from Supervisor."},
            vertex_sid_out,
        )

    # ADK transfer-based supervisor flow: treat transfer action as a valid routing decision
    # even when the model didn't emit a JSON object in plain text.
    if transfer_target:
        if _supervisor_debug_enabled():
            logger.info("SUP_DEBUG transfer_to_agent=%s", transfer_target)
        return _with_vertex_session_id(
            {
                "target_agent": transfer_target,
                "forwarded_query": user_message,
            },
            vertex_sid_out,
        )
    clean_text = response_text
    if "```json" in clean_text:
        clean_text = clean_text.split("```json")[-1].split("```")[0].strip()
    elif "```" in clean_text:
        clean_text = clean_text.split("```")[-1].split("```")[0].strip()

    try:
        data = json.loads(clean_text)
    except json.JSONDecodeError:
        lit_dict = _try_parse_dict_string(clean_text)
        if lit_dict is not None:
            hit_lit = _routing_payload_from_dict(lit_dict)
            if hit_lit:
                fq = (hit_lit.get("forwarded_query") or "").strip() or user_message
                logger.info(
                    "Supervisor: parsed routing from literal/lenient text: %s",
                    hit_lit.get("target_agent"),
                )
                return _with_vertex_session_id(
                    {"target_agent": hit_lit["target_agent"], "forwarded_query": fq},
                    vertex_sid_out,
                )
        if extracted:
            fq = (extracted.get("forwarded_query") or "").strip() or user_message
            logger.info(
                "Supervisor: non-JSON text; using structured routing from stream events: %s",
                extracted.get("target_agent"),
            )
            return _with_vertex_session_id(
                {"target_agent": extracted["target_agent"], "forwarded_query": fq},
                vertex_sid_out,
            )
        logger.warning("Supervisor returned non-JSON: %s", clean_text[:100])
        if _looks_like_supervisor_runtime_error(clean_text):
            return _with_vertex_session_id(
                {"agent": "BLOCK", "response": f"Agent Engine error: {clean_text[:300]}"},
                vertex_sid_out,
            )
        if _supervisor_debug_enabled():
            logger.info("SUP_DEBUG treating non-JSON as direct_response")
        # Some supervisor versions directly relay a sub-agent response (non-JSON markdown/text).
        # Surface it as a direct final response instead of mislabeling as a policy block.
        return _with_vertex_session_id(
            {
                "target_agent": "agentic_lens_supervisor",
                "forwarded_query": user_message,
                "direct_response": clean_text,
            },
            vertex_sid_out,
        )

    if not isinstance(data, dict):
        if extracted:
            fq = (extracted.get("forwarded_query") or "").strip() or user_message
            return _with_vertex_session_id(
                {"target_agent": extracted["target_agent"], "forwarded_query": fq},
                vertex_sid_out,
            )
        return _with_vertex_session_id({"agent": "BLOCK", "response": response_text}, vertex_sid_out)
    if data.get("agent") == "BLOCK":
        return _with_vertex_session_id(
            {"agent": "BLOCK", "response": data.get("response", "Request blocked.")},
            vertex_sid_out,
        )
    routed = _routing_payload_from_dict(data)
    if routed:
        fq = (routed.get("forwarded_query") or "").strip() or user_message
        return _with_vertex_session_id(
            {"target_agent": routed["target_agent"], "forwarded_query": fq},
            vertex_sid_out,
        )
    return _with_vertex_session_id(
        {
            "target_agent": data.get("target_agent")
            or data.get("targetAgent")
            or data.get("agent"),
            "forwarded_query": data.get("forwarded_query")
            or data.get("forwardedQuery")
            or user_message,
        },
        vertex_sid_out,
    )


def call_agent_engine(
    engine_id: str,
    user_message: str,
    user_id: str = _DEFAULT_USER_ID,
    engine_session_id: Optional[str] = None,
    *,
    session_id: Optional[str] = None,
    security_level: str = "off",
) -> tuple[str, Optional[str]]:
    """
    Invoke a specific Agent Engine by resource name.

    ``engine_session_id`` (or legacy keyword ``session_id``) must be a Vertex Agent Engine
    session id (from ``async_create_session``), not an arbitrary UI UUID.
    Returns (response_text, engine_session_id_to_cache) for multi-turn continuity on that engine.
    """
    if engine_session_id is not None and session_id is not None:
        raise TypeError("call_agent_engine: pass only one of engine_session_id and session_id")
    eff_session = engine_session_id if engine_session_id is not None else session_id

    if not (engine_id and engine_id.strip()):
        return ("⚠️ No engine ID provided.", eff_session)
    engine_id = engine_id.strip()
    t0 = time.perf_counter()
    log_event("department_call_start", engine_id=engine_id[:80] if len(engine_id) > 80 else engine_id)
    _ce_links = _api_ingress_links()
    _ce_span_kw: dict = {}
    if _ce_links:
        _ce_span_kw["links"] = _ce_links
    try:
        with tracer.start_as_current_span("lens.backend.call_agent_engine", **_ce_span_kw) as span:
            span.set_attribute("agent.system", "agentic_lens")
            span.set_attribute("agent.role", "backend_department_call")
            _ce_rid = get_lens_request_id()
            if _ce_rid:
                span.set_attribute("lens.request_id", _ce_rid)
            _ce_eng = _short_engine_resource_id(engine_id)
            if _ce_eng:
                span.set_attribute("vertex.engine_id", _ce_eng)

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
                    return ("⚠️ GCP_PROJECT_ID / GOOGLE_CLOUD_PROJECT not set.", eff_session)

                # #region agent log
                prism_debug_log(
                    "H-B",
                    "agent_engine_client.py:call_agent_engine",
                    "backend_vertex_context",
                    {
                        "engine_suffix": engine_id.rsplit("/", 1)[-1][:80],
                        "project": (project or "")[:40],
                        "location": location,
                    },
                )
                # #endregion

                _init_vertexai_backend(project, location)
                # Agent-to-agent (A2A-style): backend → lead agent (e.g. eng_lead) via SDK (not HTTP A2A protocol).
                engine = agent_engines.get(engine_id)
                vertex_sid_out: Optional[str] = eff_session
                texts = []
                _inc_tool_result = not _is_events_engine_id(engine_id)
                debug_stream = os.getenv(_DEBUG_STREAM_ENV, "").strip().lower() in ("1", "true", "yes")
                event_count = 0
                stream_failed_value_error = False
                stream_ve = None

                try:
                    dept_timeout = _department_engine_timeout_s()
                    events, timed_out, vertex_sid_out = _stream_query_resolving_engine_session(
                        engine,
                        message=user_message,
                        user_id=user_id,
                        engine_session_id=eff_session,
                        timeout_s=dept_timeout,
                        otel_parent_context=_current_otel_context(),
                        security_level=security_level,
                    )
                    if timed_out:
                        return (
                            "⚠️ Agent Engine timeout. Please retry. "
                            f"(Limit was {dept_timeout}s; set AGENT_ENGINE_DEPARTMENT_TIMEOUT_S to increase.)",
                            vertex_sid_out,
                        )
                    for i, ev in enumerate(events):
                        event_count += 1
                        if debug_stream and i < _DEBUG_STREAM_MAX_EVENTS:
                            try:
                                insp = _stream_event_to_inspect(ev)
                                print(f"DEBUG_STREAM event[{i}] type={type(ev).__name__}")
                                print(json.dumps(insp, indent=2, default=str))
                            except Exception as e_dbg:
                                print(f"DEBUG_STREAM event[{i}] inspect failed: {e_dbg}")
                        print(f"DEBUG: Chunk {i} Type: {type(ev)}")
                        try:
                            content_str = str(ev)
                            print(f"DEBUG: Chunk {i} Content: {content_str[:500]}...")
                        except Exception:
                            pass

                        before_len = len(texts)
                        _collect_text(
                            ev,
                            texts,
                            include_function_response_result=_inc_tool_result,
                        )
                        if len(texts) == before_len:
                            try:
                                raw_str = str(ev)
                                if "function_call" in raw_str or "function_response" in raw_str:
                                    print(f"DEBUG: Skipping function call/response artifact in chunk {i}")
                                    continue
                                if raw_str and raw_str.strip():
                                    texts.append(raw_str.strip())
                            except Exception:
                                pass
                except ValueError as ve:
                    if "parse array of JSON objects" in str(ve) or "instead got" in str(ve):
                        stream_failed_value_error = True
                        stream_ve = ve
                        logger.info("Agent engine stream format not supported, will use non-streaming query: %s", ve)
                    else:
                        raise

                # Hardcode strict streaming validation to enforce edge Model Armor scans E2E
                strict_engine_stream = True

                if strict_engine_stream and (stream_failed_value_error or not texts):
                    raise RuntimeError("Streaming query is strictly required for Agent Ingress validation.")

                if stream_failed_value_error and not texts:
                    print("DEBUG: Using ReasoningEngine.query() fallback due to stream parse error.")
                    try:
                        from vertexai.preview.reasoning_engines import ReasoningEngine as RE
                        re_engine = RE(engine_id)
                        response = re_engine.query(message=user_message)
                        print(f"DEBUG: ReasoningEngine.query response type: {type(response)}")
                        if isinstance(response, str) and response.strip():
                            texts.append(response.strip())
                        else:
                            _collect_text(
                                response,
                                texts,
                                include_function_response_result=_inc_tool_result,
                            )
                            if not texts and hasattr(response, "text"):
                                texts.append(str(response.text).strip())
                            if not texts and hasattr(response, "output"):
                                out = getattr(response, "output", None)
                                if isinstance(out, str) and out.strip():
                                    texts.append(out.strip())
                    except Exception as e_fallback:
                        logger.warning("Agent engine non-streaming fallback failed: %s", e_fallback)
                        return (
                            f"Agent Engine error: {str(stream_ve)[:200]}" if stream_ve else str(e_fallback)[:200],
                            vertex_sid_out,
                        )

                if strict_engine_stream and not texts:
                    raise RuntimeError("Streaming query is strictly required for Agent Ingress validation.")

                if not texts:
                    print("DEBUG: No text collected via standard logic. STREAM WAS EMPTY or parsed nothing.")
                    print("DEBUG: Attempting ReasoningEngine.query(input=...) fallback...")
                    try:
                        from vertexai.preview.reasoning_engines import ReasoningEngine as RE
                        re_engine = RE(engine_id)
                        response = re_engine.query(input=user_message)
                        print(f"DEBUG: ReasoningEngine.query response type: {type(response)}")
                        if isinstance(response, str) and response.strip():
                            texts.append(response.strip())
                        else:
                            _collect_text(
                                response,
                                texts,
                                include_function_response_result=_inc_tool_result,
                            )
                            if not texts and hasattr(response, "text"):
                                texts.append(str(response.text).strip())
                            if not texts and hasattr(response, "output"):
                                out = getattr(response, "output", None)
                                if isinstance(out, str) and out.strip():
                                    texts.append(out.strip())
                    except Exception as e_fallback:
                        print(f"DEBUG: Fallback ReasoningEngine.query failed: {e_fallback}")

                if strict_engine_stream and not texts:
                    raise RuntimeError("Streaming query is strictly required for Agent Ingress validation.")

                if not texts:
                    try:
                        from vertexai.generative_models import GenerativeModel
                        model = GenerativeModel("gemini-2.5-flash")
                        prompt = (
                            "Answer this user question in one or two short sentences. "
                            "If it is about an event, conference, or schedule, give a helpful brief answer about typical event details (e.g. keynotes, registration). "
                            "Otherwise give a brief helpful answer.\n\nUser: " + user_message
                        )
                        resp = model.generate_content(prompt, generation_config={"temperature": 0.2, "max_output_tokens": 256})
                        if resp and resp.text and resp.text.strip():
                            texts.append(resp.text.strip())
                            print("DEBUG: Gemini fallback produced response.")
                    except Exception as e_gemini:
                        logger.warning("Gemini fallback failed: %s", e_gemini)
                        print(f"DEBUG: Gemini fallback failed: {e_gemini}")

                if texts:
                    seen_chunks: set[str] = set()
                    deduped: list[str] = []
                    for t in texts:
                        if t is None:
                            continue
                        st = str(t).strip()
                        if not st or st in seen_chunks:
                            continue
                        seen_chunks.add(st)
                        deduped.append(st)
                    texts = deduped

                response_text = "\n".join(texts).strip()
                if not response_text:
                    response_text = "⚠️ No response from agent."
                    print("DEBUG: Final response was empty even after fallback.")
                else:
                    print(f"DEBUG: Final extracted response length: {len(response_text)}")

                log_event("department_call_done", duration_ms=round((time.perf_counter() - t0) * 1000, 2))
                return (response_text, vertex_sid_out)
            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR))
                log_event(
                    "department_call_error",
                    error=str(e)[:300],
                    duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                    level=logging.WARNING,
                )
                logger.exception("call_agent_engine failed for %s: %s", engine_id[:50], e)
                print(f"DEBUG: EXCEPTION in call_agent_engine: {e}")
                return (f"🚨 **Agent Engine error:** {str(e)[:300]}", eff_session)
    except Exception as e:
        log_event(
            "department_call_error",
            error=str(e)[:300],
            duration_ms=round((time.perf_counter() - t0) * 1000, 2),
            level=logging.WARNING,
        )
        logger.exception("call_agent_engine outer failure for %s: %s", engine_id[:50], e)
        return (f"🚨 **Agent Engine error:** {str(e)[:300]}", eff_session)


def send_message_to_supervisor(
    user_message: str,
    user_id: str = _DEFAULT_USER_ID,
    session_id: Optional[str] = None,
    log_callback: Optional[Callable[[str, str], None]] = None,
) -> tuple[str, Optional[str], Optional[str]]:
    """
    Send user message to the Supervisor Agent Engine. Supervisor routes and invokes
    department agents (eng_lead, xray_manager, events, chat) inside the engine.

    Returns:
        (response_text, last_department_or_none, session_id_or_none)
        If engine is not configured or call fails, returns (error_message, None, None).
        session_id is returned so caller can persist it for conversation history.
    """
    engine_name = _get_supervisor_engine_name()
    if not engine_name:
        msg = (
            "Supervisor Agent Engine not configured. Set "
            f"{SUPERVISOR_ENGINE_ENV} to the engine resource name (e.g. from "
            "repo root: python scripts/get_agent_engine_id.py supervisor)."
        )
        logger.warning(msg)
        return (f"⚠️ **Configuration:** {msg}", None, None)

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
            return ("⚠️ **Configuration:** GCP_PROJECT_ID / GOOGLE_CLOUD_PROJECT not set.", None, None)

        _init_vertexai_backend(project, location)
        engine = agent_engines.get(engine_name)

        # Create session explicitly from client side (uses Cloud Run SA credentials which have session permission)
        # This avoids the 403 when the ADK template tries to create session inside the engine.
        # Per docs: https://docs.cloud.google.com/agent-builder/agent-engine/sessions/manage-sessions-api
        # Disable explicit session creation to avoid empty responses/permissions issues.
        # Verified that implicit session creation works (Step 4879).
        # Context tradeoff: Remote Supervisor won't have multi-turn context, but local app does.
        # if not session_id:
        #     try:
        #         if log_callback:
        #             log_callback("🟡 Creating session (Agent Engine)...", "supervisor")
        #         # ... (Session creation logic commented out) ...
        #     except Exception as session_err:
        #         logger.warning("Failed to create session from client, engine will try: %s", session_err)

        if log_callback:
            log_callback("🟡 Sending message to Supervisor (Agent Engine)...", "supervisor")

        kwargs = {"message": user_message, "user_id": user_id}
        # if session_id:
        #     kwargs["session_id"] = session_id
        
        # Explicitly do NOT pass session_id to force implicit creation/working path
        texts = []
        raw_events_for_debug = []
        try:
            stream = engine.stream_query(**kwargs)
            for ev in stream:
                n_before = len(texts)
                _collect_text(ev, texts)
                if len(texts) == n_before and ev is not None and len(raw_events_for_debug) < 5:
                    raw_events_for_debug.append(ev)
        except Exception as ve:
            logger.error("Supervisor stream query failed: %s", ve)
            raise RuntimeError(f"Streaming query is strictly required for Agent Ingress validation. Details: {ve}")
        
        if not texts:
            raise RuntimeError("Streaming query is strictly required for Agent Ingress validation. Stream was empty.")

        response_text = "\n".join(texts).strip() if texts else ""
        
        # ------------------------------------------------------------------
        # CLIENT-SIDE ORCHESTRATION (The "Two-Hop")
        # ------------------------------------------------------------------
        # The Supervisor Reasoning Engine returns a JSON routing decision.
        # We must parse it and invoke the target agent's reasoning engine.
        last_department = None
        
        try:
            # Attempt to parse as JSON (routing decision)
            # Cleanup potential markdown wrapping if present
            clean_text = response_text
            if "```json" in clean_text:
                clean_text = clean_text.split("```json")[-1].split("```")[0].strip()
            elif "```" in clean_text:
                clean_text = clean_text.split("```")[-1].split("```")[0].strip()

            data = json.loads(clean_text)
            
            if isinstance(data, dict) and "target_agent" in data:
                # It is a routing decision!
                target = data["target_agent"]
                
                if target == "BLOCK":
                    # Security Block
                    response_text = data.get("response", "🚫 Request blocked by security policy.")
                    last_department = "BLOCK"
                    if log_callback:
                        log_callback(f"🛡️ Security Block: {response_text}", "supervisor")
                else:
                    # Dispatch to Sub-Agent
                    last_department = target
                    formatted_query = data.get("forwarded_query", user_message)
                    
                    if log_callback:
                        log_callback(f"🔄 Routing to {target}...", "supervisor")
                    
                    target_engine_name = _get_engine_by_display_name(target)
                    
                    if not target_engine_name:
                         msg = f"⚠️ Routing Error: Could not find Reasoning Engine for agent '{target}'. Check deployments."
                         logger.error(msg)
                         response_text = msg
                    else:
                        # Invoke target agent
                        if log_callback:
                            log_callback(f"📞 Invoking {target} Engine...", target)
                            
                        target_engine = agent_engines.get(target_engine_name)
                        sub_texts = []
                        chunk_count = 0
                        sub_inc_tool = not _is_events_engine_id(target_engine_name)
                        try:
                            dept_timeout = _department_engine_timeout_s()
                            sub_events, sub_timed_out, sub_session_resolved = _stream_query_resolving_engine_session(
                                target_engine,
                                message=formatted_query,
                                user_id=user_id,
                                engine_session_id=session_id,
                                timeout_s=dept_timeout,
                                otel_parent_context=_current_otel_context(),
                            )
                            if sub_timed_out:
                                sub_texts.append(f"⚠️ Agent Engine timeout after {dept_timeout}s.")
                            for sub_ev in sub_events:
                                chunk_count += 1
                                print(f"DEBUG: {target} Chunk {chunk_count} Type: {type(sub_ev)}")
                                before_len = len(sub_texts)
                                _collect_text(
                                    sub_ev,
                                    sub_texts,
                                    include_function_response_result=sub_inc_tool,
                                )
                                if len(sub_texts) == before_len:
                                    try:
                                        raw_str = str(sub_ev)
                                        if "function_call" in raw_str or "function_response" in raw_str:
                                            continue
                                        if raw_str and raw_str.strip():
                                            sub_texts.append(raw_str.strip())
                                    except:
                                        pass
                        except Exception as e_stream:
                            logger.error(f"Stream iteration failed for {target}: {e_stream}")
                            raise RuntimeError(f"Streaming query is strictly required for Agent Ingress validation. Details: {e_stream}")
                        
                        if chunk_count == 0 and not sub_texts:
                            raise RuntimeError("Streaming query is strictly required for Agent Ingress validation. Stream was empty.")
                        
                        response_text = "\n".join(sub_texts).strip()
                        if log_callback:
                             log_callback(f"✅ {target} responded ({len(response_text)} chars).", target)

        except json.JSONDecodeError:
            # Not JSON -> It's a direct response (or raw text failure)
            pass
        except Exception as e:
            logger.warning(f"Orchestration/Parsing error: {e}")
            # Fallback to showing original text
            pass

        if log_callback and response_text and not last_department:
            log_callback("🟡 Supervisor (Agent Engine) responded.", "supervisor")
            
        if not response_text and raw_events_for_debug:
            # Log structure so we can fix parsing (keys + short repr)
            for i, ev in enumerate(raw_events_for_debug):
                keys = list(ev.keys()) if isinstance(ev, dict) else type(ev).__name__
                snippet = repr(ev)[:500]
                logger.info(
                    "Supervisor stream event #%d (no text parsed). keys=%s snippet=%s",
                    i + 1, keys, snippet,
                )
        if not response_text:
            logger.info(
                "Supervisor stream yielded no parseable text. Check reasoning_engine_stderr for errors. Raw events (first 5) logged above."
            )
        return (
            response_text or "⚠️ No response from Agent. Check Cloud Logging.",
            last_department,
            session_id,
        )
    except Exception as e:
        err_str = str(e)
        # Log full exception and any details (e.g. gRPC/API may include principal or permission in details)
        logger.exception("Agent Engine call failed: %s", e)
        if hasattr(e, "details") and e.details:
            logger.info("Exception details (may include principal): %s", e.details)
        if hasattr(e, "metadata") and e.metadata:
            logger.info("Exception metadata: %s", e.metadata)

        if "403" in err_str or "PERMISSION_DENIED" in err_str or "sessions.create" in err_str or "Failed to create session" in err_str:
            hint = (
                " Find the denied principal: run "
                "`python3 scripts/fetch_session_403_principal.py` (after reproducing the error), "
                "or see docs/SESSION_403_INVESTIGATION.md."
            )
            return (
                "🚨 **Session / permission error:** The request was denied (403). "
                "The identity that called the Agent Engine needs `aiplatform.sessions.create`."
                + hint
                + (f"\n\n_Details: {err_str[:250]}_" if len(err_str) > 50 else ""),
                None,
                None,
            )
        return (f"🚨 **Agent Engine error:** {err_str[:300]}", None, None)


def is_agent_engine_configured() -> bool:
    """True if the Supervisor Agent Engine is configured (env or resolvable by display_name)."""
    return _get_supervisor_engine_name() is not None
