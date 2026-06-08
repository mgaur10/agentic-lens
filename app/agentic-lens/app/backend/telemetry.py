"""
OpenTelemetry bootstrap and Lens helpers.

Span attribute conventions (stable names for Cloud Trace / Log Explorer):

- ``lens.request_id`` — UUID generated at ``lens.api.query`` ingress; correlate API, backend, agents.
- ``session.id`` — Glass UI / browser session (not Vertex engine session).
- ``vertex.session_id`` — Server-issued Agent Engine session id when known.
- ``vertex.engine_id`` — Short suffix of ``projects/.../reasoningEngines/…`` resource name.
- ``agent.system`` — ``agentic_lens``
- ``department`` — e.g. ``api``, ``supervisor``, ``engineering``
- ``agent.role`` — e.g. ``ingress``, ``supervisor``, ``lead``
"""
import logging
import os
import re
from typing import Dict, Optional, Tuple

try:
    from opentelemetry import propagate, trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    _OTEL_AVAILABLE = True
except Exception:
    propagate = None
    trace = None
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    _OTEL_AVAILABLE = False

logger = logging.getLogger(__name__)

_TELEMETRY_INITIALIZED = False
_TRACEPARENT_MARKER_PREFIX = "<!-- LENS_TRACEPARENT:"
_TRACEPARENT_MARKER_SUFFIX = "-->"
_TRACESTATE_MARKER_PREFIX = "<!-- LENS_TRACESTATE:"
_TRACESTATE_MARKER_SUFFIX = "-->"
_LENS_REQUEST_ID_MARKER_PREFIX = "<!-- LENS_REQUEST_ID:"
_LENS_REQUEST_ID_MARKER_SUFFIX = "-->"
_LENS_REQUEST_ID_LINE_RE = re.compile(
    r"^\s*<!--\s*LENS_REQUEST_ID:([^>]+?)\s*-->\s*\n?",
    re.IGNORECASE,
)


def init_otel(service_name: str) -> None:
    """Initialize OTel once for this process."""
    global _TELEMETRY_INITIALIZED
    if _TELEMETRY_INITIALIZED:
        return
    if not _OTEL_AVAILABLE:
        logger.warning("OpenTelemetry packages not available; telemetry disabled.")
        _TELEMETRY_INITIALIZED = True
        return
    try:
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.namespace": os.getenv("OTEL_SERVICE_NAMESPACE", "agentic_lens"),
            }
        )
        provider = TracerProvider(resource=resource)
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            exporter = CloudTraceSpanExporter()
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except Exception as e:
            logger.warning("Cloud Trace exporter init failed: %s", e)
        trace.set_tracer_provider(provider)

        # Best-effort Vertex AI auto-instrumentation.
        try:
            from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor

            VertexAIInstrumentor().instrument()
        except Exception as e:
            logger.info("VertexAI auto-instrumentation unavailable: %s", e)
        _TELEMETRY_INITIALIZED = True
    except Exception as e:
        logger.warning("OTel initialization failed: %s", e)


def get_tracer(name: str = "agentic_lens"):
    if not _OTEL_AVAILABLE:
        class _NoopSpan:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def set_attribute(self, *_): return None
            def record_exception(self, *_): return None
            def set_status(self, *_): return None

        class _NoopTracer:
            def start_as_current_span(self, *_args, **_kwargs): return _NoopSpan()
        return _NoopTracer()
    return trace.get_tracer(name)


def inject_w3c_headers() -> Dict[str, str]:
    carrier: Dict[str, str] = {}
    if not _OTEL_AVAILABLE:
        return carrier
    try:
        propagate.inject(carrier)
    except Exception:
        return {}
    return carrier


def extract_w3c_headers(traceparent: Optional[str], tracestate: Optional[str]):
    if not _OTEL_AVAILABLE:
        return None
    carrier: Dict[str, str] = {}
    if traceparent:
        carrier["traceparent"] = traceparent
    if tracestate:
        carrier["tracestate"] = tracestate
    if not carrier:
        return None
    try:
        return propagate.extract(carrier)
    except Exception:
        return None


def with_lens_trace_marker(message: str, traceparent: Optional[str], tracestate: Optional[str]) -> str:
    """Prefix message with hidden Lens W3C trace markers for cross-engine propagation."""
    if not traceparent:
        return message
    if message.startswith(_TRACEPARENT_MARKER_PREFIX):
        return message
    prefix = f"{_TRACEPARENT_MARKER_PREFIX}{traceparent}{_TRACEPARENT_MARKER_SUFFIX}\n"
    if tracestate:
        prefix += f"{_TRACESTATE_MARKER_PREFIX}{tracestate}{_TRACESTATE_MARKER_SUFFIX}\n"
    return prefix + message


def extract_lens_trace_marker(message: str) -> Tuple[Optional[str], Optional[str], str]:
    """Extract Lens W3C trace markers and return (traceparent, tracestate, cleaned_message)."""
    if not message:
        return (None, None, message)
    traceparent = None
    tracestate = None
    lines = message.splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if line.startswith(_TRACEPARENT_MARKER_PREFIX) and line.endswith(_TRACEPARENT_MARKER_SUFFIX):
            traceparent = line[len(_TRACEPARENT_MARKER_PREFIX) : -len(_TRACEPARENT_MARKER_SUFFIX)].strip()
            idx += 1
            continue
        if line.startswith(_TRACESTATE_MARKER_PREFIX) and line.endswith(_TRACESTATE_MARKER_SUFFIX):
            tracestate = line[len(_TRACESTATE_MARKER_PREFIX) : -len(_TRACESTATE_MARKER_SUFFIX)].strip()
            idx += 1
            continue
        break
    cleaned = "\n".join(lines[idx:]) if idx else message
    return (traceparent, tracestate, cleaned)


def with_lens_request_id_marker(message: str, request_id: Optional[str]) -> str:
    """Prefix with hidden comment so remote Agent Engine agents can record lens.request_id; strip before LLM."""
    if not request_id or not (message or "").strip():
        return message or ""
    raw = message or ""
    if raw.lstrip().startswith(_LENS_REQUEST_ID_MARKER_PREFIX):
        return raw
    return f"{_LENS_REQUEST_ID_MARKER_PREFIX}{request_id}{_LENS_REQUEST_ID_MARKER_SUFFIX}\n{raw}"


def extract_lens_request_id_marker(message: str) -> Tuple[Optional[str], str]:
    """Return (request_id_or_none, message_without_marker_line)."""
    if not message:
        return (None, message)
    m = _LENS_REQUEST_ID_LINE_RE.match(message)
    if not m:
        return (None, message)
    rid = (m.group(1) or "").strip() or None
    return (rid, message[m.end() :])
