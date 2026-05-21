"""Debug session NDJSON: workspace log file + stdout for Cloud Logging (logger prism.debug)."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

_LOG_PATH = "/home/mgaur/Desktop/workspace-mg/vibe-coding/agentic-prism-v3/.cursor/debug-8a1afa.log"
_SESSION_ID = "8a1afa"
_logger = logging.getLogger("prism.debug")


def prism_debug_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: Dict[str, Any],
    run_id: str = "pre-fix",
) -> None:
    payload = {
        "sessionId": _SESSION_ID,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    line = json.dumps(payload, default=str)
    _logger.warning("PRISM_DEBUG_NDJSON %s", line)
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
