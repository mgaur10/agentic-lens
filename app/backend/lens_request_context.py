"""
Per-request correlation for Lens tracing and structured logs.

``lens.request_id`` is generated at API ingress and propagated via contextvars through
the Glass UI process (FastAPI → agent_engine_client). Remote Agent Engine runtimes also
receive the same id via a hidden HTML comment stripped before LLM/routing (see glass_ui_api).
"""
from __future__ import annotations

import contextvars
from typing import Any, Optional

# UUID string; set at /api/query entry, reset in finally.
lens_request_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "lens_request_id", default=None
)

# SpanContext from lens.api.query — used for OTel span links on backend engine spans.
_lens_api_root_span_context: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "_lens_api_root_span_context", default=None
)


def get_lens_request_id() -> Optional[str]:
    return lens_request_id.get()


def set_lens_request_id(value: str) -> contextvars.Token:
    return lens_request_id.set(value)


def reset_lens_request_id(token: contextvars.Token) -> None:
    lens_request_id.reset(token)


def set_lens_api_root_span_context(ctx: Any) -> contextvars.Token:
    return _lens_api_root_span_context.set(ctx)


def get_lens_api_root_span_context() -> Any:
    return _lens_api_root_span_context.get()


def reset_lens_api_root_span_context(token: contextvars.Token) -> None:
    _lens_api_root_span_context.reset(token)
