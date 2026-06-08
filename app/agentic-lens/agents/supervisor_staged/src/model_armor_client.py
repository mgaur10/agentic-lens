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
    modelarmor_v1 = None
    ClientOptions = None
    _AVAILABLE = False


def _model_armor_location() -> str:
    """Region for Model Armor API; use us-east4 when running in us-east5 (Model Armor not in us-east5)."""
    loc = (
        os.getenv("MODEL_ARMOR_LOCATION")
        or os.getenv("MODEL_ARMOR_REGION")
        or os.getenv("GCP_LOCATION")
        or os.getenv("REGION")
        or "us-central1"
    ).strip()
    if loc == "us-east5":
        return "us-east4"
    return loc


def _template_name(security_level: str) -> str | None:
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
    location = _model_armor_location()
    if not project_id:
        return None
    override = (os.getenv("MODEL_ARMOR_TEMPLATE") or "").strip()
    if override:
        return f"projects/{project_id}/locations/{location}/templates/{override}"
    if security_level == "medium":
        return f"projects/{project_id}/locations/{location}/templates/security-medium"
    if security_level == "high":
        return f"projects/{project_id}/locations/{location}/templates/security-high"
    return None


class ModelArmorClient:
    """
    Client for Model Armor (SDK). Used by Supervisor for security gate.
    sanitize(user_query, security_level) maps security_level to template_id
    (medium → security-medium, high → security-high) and calls the API.
    """

    def sanitize_user_prompt(
        self, user_query: str, template_id: str | None = None
    ) -> dict[str, Any]:
        """
        Sanitize user prompt with the given template_id (e.g. security-medium, security-high).
        If template_id is None or "off", returns no block.
        """
        level = (template_id or "").strip().lower()
        if level in ("", "off"):
            return {"block": False}
        if level in ("security-medium", "medium"):
            level = "medium"
        elif level in ("security-high", "high"):
            level = "high"
        return self.sanitize(user_query, level)

    def sanitize(self, user_query: str, security_level: str) -> dict[str, Any]:
        """
        Sanitize user query with Model Armor. If blocked, return BLOCK; else pass (optional sanitized text).

        Returns:
            {"block": True, "reason": "..."} on security violation.
            {"block": False} or {"block": False, "sanitized_prompt": str} on pass.
        """
        if not security_level or security_level == "off":
            return {"block": False}

        if not _AVAILABLE or modelarmor_v1 is None:
            return {"block": False}

        template_name_val = _template_name(security_level)
        if not template_name_val:
            return {"block": False}

        location = (os.getenv("GCP_LOCATION") or "us-central1").strip()
        try:
            client = modelarmor_v1.ModelArmorClient(
                transport="rest",
                client_options=ClientOptions(
                    api_endpoint=f"modelarmor.{location}.rep.googleapis.com"
                ),
            )
            request = modelarmor_v1.SanitizeUserPromptRequest(
                name=template_name_val,
                user_prompt_data=modelarmor_v1.DataItem(text=user_query),
            )
            response = client.sanitize_user_prompt(request=request)
        except Exception:
            return {"block": False}

        sanitization_result = getattr(response, "sanitization_result", None)
        if not sanitization_result:
            return {"block": False}

        filter_match_state = getattr(sanitization_result, "filter_match_state", None)
        match_found = (
            filter_match_state == 2
            or (hasattr(filter_match_state, "name") and getattr(filter_match_state, "name", "") == "MATCH_FOUND")
            or str(filter_match_state) == "MATCH_FOUND"
            or getattr(filter_match_state, "value", None) == 2
        )

        if match_found:
            return {"block": True, "reason": "Security Violation"}

        # Pass; optionally return sanitized prompt if SDP redacted content
        sanitized = None
        try:
            for key, val in (getattr(sanitization_result, "filter_results", None) or {}).items():
                if not hasattr(val, "sdp_filter_result") or val.sdp_filter_result is None:
                    continue
                sdp = val.sdp_filter_result
                if not getattr(sdp, "deidentify_result", None) or sdp.deidentify_result is None:
                    continue
                data = getattr(sdp.deidentify_result, "data", None)
                if data is not None and hasattr(data, "text") and (data.text or "").strip():
                    sanitized = data.text.strip()
                    break
        except Exception:
            pass

        out: dict[str, Any] = {"block": False}
        if sanitized:
            out["sanitized_prompt"] = sanitized
        return out
