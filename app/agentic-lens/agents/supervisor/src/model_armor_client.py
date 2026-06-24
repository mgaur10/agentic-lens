"""
Model Armor client for Supervisor security gate.
Exposes sanitize(user_query, security_level) — returns BLOCK or pass (optional sanitized text).
"""
import os
from typing import Any

try:
    from google.api_core.client_options import ClientOptions
    from google.cloud import modelarmor_v1
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

def _model_armor_location() -> str:
    return os.environ.get("MODEL_ARMOR_LOCATION", "us-central1")

def _template_name() -> str:
    return os.environ.get("MODEL_ARMOR_TEMPLATE_NAME", "")

class ModelArmorClient:
    """Thin wrapper around the Model Armor API."""

    def __init__(self):
        self._available = _AVAILABLE
        self._client = None
        if _AVAILABLE and _template_name():
            try:
                opts = ClientOptions(
                    api_endpoint=f"{_model_armor_location()}-modelarmor.googleapis.com"
                )
                self._client = modelarmor_v1.ModelArmorClient(client_options=opts)
            except Exception:
                self._available = False

    def sanitize(self, user_query: str, security_level: str = "standard") -> dict[str, Any]:
        """Returns {'action': 'BLOCK'|'PASS', 'sanitized_prompt': str|None}"""
        if not self._available or not self._client or not _template_name():
            return {"action": "PASS", "sanitized_prompt": None}
        try:
            request = modelarmor_v1.SanitizeUserPromptRequest(
                name=_template_name(),
                user_prompt_data=modelarmor_v1.DataItem(text=user_query),
            )
            response = self._client.sanitize_user_prompt(request=request)
            verdict = response.sanitization_result.filter_match_state.name
            if verdict == "MATCH_FOUND":
                return {"action": "BLOCK", "sanitized_prompt": None}
            return {"action": "PASS", "sanitized_prompt": None}
        except Exception:
            return {"action": "PASS", "sanitized_prompt": None}
