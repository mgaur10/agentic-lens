"""
Strip Glass UI hidden markers before LLM and record ``lens.request_id`` spans for department LlmAgents.
Parents LLM spans under W3C context from Glass ingress when traceparent comments are present.
"""
from __future__ import annotations

import contextvars
import logging
import re
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple

try:
    from telemetry import get_tracer
except ImportError:
    from .telemetry import get_tracer

if TYPE_CHECKING:
    from google.adk.agents import LlmAgent

logger = logging.getLogger(__name__)
tracer = get_tracer()

_RE_LENS_RID = re.compile(r"^\s*<!--\s*LENS_REQUEST_ID:([^>]+?)\s*-->\s*\n?", re.IGNORECASE)
_RE_TP = re.compile(r"^\s*<!--\s*LENS_TRACEPARENT:([^>]+?)\s*-->\s*\n?", re.IGNORECASE)
_RE_TS = re.compile(r"^\s*<!--\s*LENS_TRACESTATE:([^>]+?)\s*-->\s*\n?", re.IGNORECASE)
_RE_PRISM = re.compile(r"^\s*<!--\s*PRISM_SESSION_ID:([^>]+?)\s*-->\s*\n?", re.IGNORECASE)


def _strip_department_prefixes(
    text: str,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
    """Strip markers in wire order; return (lens_rid, traceparent, tracestate, ui_session_id, body)."""
    lens_rid = None
    traceparent = None
    tracestate = None
    ui_sid = None
    rest = text or ""
    while True:
        m = _RE_LENS_RID.match(rest)
        if m:
            lens_rid = (m.group(1) or "").strip() or lens_rid
            rest = rest[m.end() :]
            continue
        m = _RE_TP.match(rest)
        if m:
            traceparent = (m.group(1) or "").strip() or traceparent
            rest = rest[m.end() :]
            continue
        m = _RE_TS.match(rest)
        if m:
            tracestate = (m.group(1) or "").strip() or tracestate
            rest = rest[m.end() :]
            continue
        m = _RE_PRISM.match(rest)
        if m:
            ui_sid = (m.group(1) or "").strip() or ui_sid
            rest = rest[m.end() :]
            continue
        break
    return (lens_rid, traceparent, tracestate, ui_sid, rest)


def _mutate_last_user_text(llm_request: Any, new_text: str) -> bool:
    contents = getattr(llm_request, "contents", None) or []
    for i in range(len(contents) - 1, -1, -1):
        c = contents[i]
        role = getattr(c, "role", None)
        if role != "user":
            continue
        parts = getattr(c, "parts", None) or []
        for part in parts:
            if getattr(part, "text", None) is not None:
                part.text = new_text
                return True
        break
    return False


_llm_otel_stack: contextvars.ContextVar[Optional[List[Tuple[Any, Any]]]] = contextvars.ContextVar(
    "lens_llm_otel_stack", default=None
)

_lens_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "lens_llm_request_id", default=None
)


def _stack_push(span: Any, token: Any) -> None:
    st = _llm_otel_stack.get()
    if st is None:
        st = []
        _llm_otel_stack.set(st)
    st.append((span, token))


def _stack_pop_end() -> None:
    st = _llm_otel_stack.get()
    if not st:
        return
    span, token = st.pop()
    try:
        from opentelemetry import context as otel_context

        otel_context.detach(token)
    except Exception:
        pass
    try:
        span.end()
    except Exception:
        pass


def make_lens_department_callbacks(
    *,
    span_name: str,
    department: str,
    agent_role: str,
    agent_id: str,
    model: Optional[str] = None,
) -> Tuple[
    Callable[..., Any],
    Callable[..., Any],
    Callable[..., Any],
]:
    """Return (before_model, after_model, on_model_error) for LlmAgent."""

    def before_model(callback_context: Any, llm_request: Any):
        try:
            contents = getattr(llm_request, "contents", None) or []
            for i in range(len(contents) - 1, -1, -1):
                c = contents[i]
                if getattr(c, "role", None) != "user":
                    continue
                parts = getattr(c, "parts", None) or []
                for part in parts:
                    raw = getattr(part, "text", None)
                    if raw is None:
                        continue
                    lens_rid, tp, ts, ui_sid, cleaned = _strip_department_prefixes(str(raw))
                    part.text = cleaned

                    if lens_rid:
                        _lens_request_id.set(lens_rid)

                    remote_ctx = None
                    if tp or ts:
                        try:
                            from opentelemetry.propagate import extract as otel_extract

                            carrier: dict[str, str] = {}
                            if tp:
                                carrier["traceparent"] = tp
                            if ts:
                                carrier["tracestate"] = ts
                            remote_ctx = otel_extract(carrier)
                        except Exception as e_ctx:
                            logger.debug("lens W3C extract failed: %s", e_ctx)
                            remote_ctx = None

                    span = tracer.start_span(span_name, context=remote_ctx)
                    try:
                        span.set_attribute("agent.system", "agentic_lens")
                        span.set_attribute("department", department)
                        span.set_attribute("agent.role", agent_role)
                        if lens_rid:
                            span.set_attribute("lens.request_id", lens_rid)
                        if ui_sid:
                            span.set_attribute("session.id", str(ui_sid)[:80])
                        sess = getattr(getattr(callback_context, "session", None), "id", None)
                        if sess:
                            span.set_attribute("vertex.session_id", str(sess)[:80])
                    except Exception as e_attr:
                        logger.debug("lens span attrs: %s", e_attr)
                    try:
                        import opentelemetry.trace as ot_trace
                        from opentelemetry import context as otel_context

                        ctx = ot_trace.set_span_in_context(span)
                        tok = otel_context.attach(ctx)
                        _stack_push(span, tok)
                    except Exception as e_ot:
                        logger.debug("lens otel attach: %s", e_ot)
                        try:
                            span.end()
                        except Exception:
                            pass
                    break
                break
        except Exception as e:
            logger.warning("lens before_model strip failed: %s", e)
        return None

    def after_model(callback_context: Any, llm_response: Any):
        try:
            try:
                from lens_llm_usage import emit_llm_usage_from_response
            except ImportError:
                from .lens_llm_usage import emit_llm_usage_from_response

            sess = getattr(getattr(callback_context, "session", None), "id", None)
            emit_llm_usage_from_response(
                llm_response,
                agent_id=agent_id,
                department=department,
                agent_role=agent_role,
                model=model,
                lens_request_id=_lens_request_id.get(),
                session_id=str(sess) if sess else None,
            )
        except Exception as e:
            logger.debug("lens llm_usage emit failed: %s", e)
        _stack_pop_end()
        return None

    def on_model_error(callback_context: Any, llm_request: Any, error: Exception):
        _stack_pop_end()
        return None

    return (before_model, after_model, on_model_error)


def attach_lens_tracing_to_agent(
    agent: LlmAgent,
    *,
    span_name: str,
    department: str,
    agent_role: str,
    agent_id: Optional[str] = None,
) -> None:
    """Prepend Lens callbacks to ``LlmAgent`` (mirrors Engineering rollout for Chat / Events / X-Ray / eng_* LlmAgents)."""
    resolved_agent_id = agent_id or getattr(agent, "name", "unknown")
    resolved_model = getattr(agent, "model", None)
    bm, am, oe = make_lens_department_callbacks(
        span_name=span_name,
        department=department,
        agent_role=agent_role,
        agent_id=str(resolved_agent_id),
        model=str(resolved_model) if resolved_model else None,
    )

    def _prepend(cur, first):
        if cur is None:
            return first
        if isinstance(cur, list):
            return [first] + list(cur)
        return [first, cur]

    agent.before_model_callback = _prepend(agent.before_model_callback, bm)
    agent.after_model_callback = _prepend(agent.after_model_callback, am)
    agent.on_model_error_callback = _prepend(agent.on_model_error_callback, oe)
