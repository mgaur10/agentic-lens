"""
Structured JSON logging for Cloud Logging and alerting.
Log one line per event so you can query by event type, session_id, duration_ms, lens.request_id, etc.
"""
import json
import logging
import time
from typing import Any, Optional

from backend.lens_request_context import get_lens_request_id

_logger = logging.getLogger(__name__)


def log_event(
    event: str,
    *,
    level: int = logging.INFO,
    session_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """Emit a single JSON line for the event. Avoid logging PII in message/query."""
    payload: dict[str, Any] = {
        "event": event,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if session_id is not None:
        payload["session_id"] = session_id[:36] if len(session_id) > 36 else session_id
    rq = get_lens_request_id()
    if rq is not None and "lens_request_id" not in kwargs:
        payload["lens_request_id"] = rq
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 2)
    if error is not None:
        payload["error"] = error[:500]
    for k, v in kwargs.items():
        if v is not None and k not in payload:
            # Keep payload small; skip large or non-serializable values
            try:
                if isinstance(v, (str, int, float, bool)) or (isinstance(v, (list, dict)) and len(str(v)) < 300):
                    payload[k] = v
            except Exception:
                pass
    try:
        line = json.dumps(payload, default=str)
    except Exception:
        line = json.dumps({"event": event, "error": "serialization_failed"})
    _logger.log(level, line)
