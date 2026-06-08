"""Structured llm_usage events for per-agent token observability (Cloud Logging + log-based metrics)."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Mapping, Optional

_logger = logging.getLogger(__name__)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _field(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def parse_usage_metadata(llm_response: Any) -> dict[str, int]:
    """Extract token counts from ADK LlmResponse or Vertex GenerateContentResponse."""
    usage = _field(llm_response, "usage_metadata")
    if usage is None and hasattr(llm_response, "model_dump"):
        try:
            usage = llm_response.model_dump().get("usage_metadata")
        except Exception:
            usage = None
    if usage is None:
        return {}

    prompt = _coerce_int(
        _field(usage, "prompt_token_count") or _field(usage, "prompt_tokens")
    )
    output = _coerce_int(
        _field(usage, "candidates_token_count")
        or _field(usage, "output_token_count")
        or _field(usage, "response_token_count")
        or _field(usage, "completion_token_count")
    )
    thoughts = _coerce_int(
        _field(usage, "thoughts_token_count") or _field(usage, "thoughts_tokens")
    )
    total = _coerce_int(
        _field(usage, "total_token_count") or _field(usage, "total_tokens")
    )
    if total <= 0:
        total = prompt + output + thoughts
    return {
        "prompt_tokens": prompt,
        "output_tokens": output,
        "thoughts_tokens": thoughts,
        "total_tokens": total,
    }


def emit_llm_usage(
    *,
    agent_id: str,
    department: str,
    agent_role: str,
    model: Optional[str] = None,
    prompt_tokens: int = 0,
    output_tokens: int = 0,
    thoughts_tokens: int = 0,
    total_tokens: int = 0,
    lens_request_id: Optional[str] = None,
    session_id: Optional[str] = None,
    status: str = "ok",
    **kwargs: Any,
) -> None:
    """Emit one llm_usage JSON line per LLM completion (not per stream chunk)."""
    if total_tokens <= 0:
        total_tokens = prompt_tokens + output_tokens + thoughts_tokens
    if total_tokens <= 0:
        return

    payload: dict[str, Any] = {
        "event": "llm_usage",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent_id": agent_id,
        "department": department,
        "agent_role": agent_role,
        "model": (model or "unknown")[:80],
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "thoughts_tokens": thoughts_tokens,
        "total_tokens": total_tokens,
        "llm_call_count": 1,
        "status": status,
    }
    if lens_request_id:
        payload["lens_request_id"] = str(lens_request_id)[:80]
    if session_id:
        payload["session_id"] = str(session_id)[:36]
    for key, value in kwargs.items():
        if value is not None:
            payload[key] = value

    try:
        line = json.dumps(payload, default=str)
    except Exception:
        line = json.dumps(
            {
                "event": "llm_usage",
                "agent_id": agent_id,
                "department": department,
                "total_tokens": total_tokens,
                "status": "serialization_failed",
            }
        )
    _logger.info(line)


def emit_llm_usage_from_response(
    llm_response: Any,
    *,
    agent_id: str,
    department: str,
    agent_role: str,
    model: Optional[str] = None,
    lens_request_id: Optional[str] = None,
    session_id: Optional[str] = None,
    status: str = "ok",
) -> None:
    """Parse usage_metadata from an ADK/Vertex response and emit llm_usage."""
    usage = parse_usage_metadata(llm_response)
    if not usage.get("total_tokens"):
        return
    resolved_model = model
    if not resolved_model:
        resolved_model = _field(llm_response, "model_version") or _field(
            llm_response, "model"
        )
    emit_llm_usage(
        agent_id=agent_id,
        department=department,
        agent_role=agent_role,
        model=str(resolved_model) if resolved_model else None,
        lens_request_id=lens_request_id,
        session_id=session_id,
        status=status,
        **usage,
    )
