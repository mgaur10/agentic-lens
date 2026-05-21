import logging
import os

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_AVAILABLE = True
except Exception:
    trace = None
    Resource = None
    SDKTracerProvider = None
    BatchSpanProcessor = None
    _OTEL_AVAILABLE = False

logger = logging.getLogger(__name__)
_INITIALIZED = False


def _add_cloud_trace_processor(provider) -> None:
    try:
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

        provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
    except Exception as e:
        logger.warning("Cloud Trace exporter init failed: %s", e)


def _add_agent_engine_otlp_processor(provider) -> None:
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        creds, _ = google.auth.default()
        session = AuthorizedSession(credentials=creds)
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    session=session,
                    endpoint="https://telemetry.googleapis.com/v1/traces",
                )
            )
        )
    except Exception as e:
        logger.warning("OTLP telemetry.googleapis.com exporter failed: %s", e)


def _maybe_instrument_vertex() -> None:
    try:
        from opentelemetry.instrumentation.vertexai import VertexAIInstrumentor

        VertexAIInstrumentor().instrument()
    except Exception as e:
        logger.info("VertexAI auto-instrumentation unavailable: %s", e)


def init_otel(service_name: str) -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    if not _OTEL_AVAILABLE:
        _INITIALIZED = True
        return
    try:
        current = trace.get_tracer_provider()
        if isinstance(current, SDKTracerProvider):
            logger.info("OTel: merging Cloud Trace exporter into existing TracerProvider.")
            _add_cloud_trace_processor(current)
            _maybe_instrument_vertex()
            _INITIALIZED = True
            return

        provider = SDKTracerProvider(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "service.namespace": os.getenv("OTEL_SERVICE_NAMESPACE", "agentic_lens"),
                }
            )
        )
        _add_agent_engine_otlp_processor(provider)
        _add_cloud_trace_processor(provider)
        trace.set_tracer_provider(provider)
        _maybe_instrument_vertex()
        _INITIALIZED = True
    except Exception as e:
        logger.warning("OTel init failed: %s", e)


def get_tracer():
    if not _OTEL_AVAILABLE:

        class _NoopSpan:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def set_attribute(self, *_):
                return None

            def record_exception(self, *_):
                return None

            def set_status(self, *_):
                return None

            def end(self):
                return None

        class _NoopTracer:
            def start_span(self, *_args, **_kwargs):
                return _NoopSpan()

            def start_as_current_span(self, *_args, **_kwargs):
                return _NoopSpan()

        return _NoopTracer()
    return trace.get_tracer("agentic_lens")
