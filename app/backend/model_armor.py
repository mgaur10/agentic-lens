"""
Model Armor Gatekeeper — screens user prompts before they reach the Supervisor.
Uses Model Armor API (sanitize_user_prompt) with configurable template (medium/high).
"""

import os
from typing import Dict, List, Any

# User-facing hints for blocked categories (API filter_result keys → short hint)
BLOCKED_CATEGORY_HINTS: Dict[str, str] = {
    "sexually_explicit": "content may be sexually explicit",
    "hate_speech": "content may contain hate speech",
    "harassment": "content may be harassing",
    "dangerous": "content may promote harmful or dangerous behavior",
    "pi_and_jailbreak_filter_result": "prompt injection or jailbreak attempt detected",
    "malicious_uri_filter_result": "malicious or unsafe link detected",
    "rai_filter_type_results": "content did not meet our responsible AI policy",
    "model_armor filter match": "content triggered a safety filter",
    "model armor filter match": "content triggered a safety filter",
}


def reason_to_hints(reason: List[str]) -> List[str]:
    """Map API reason keys to user-facing hints for the blocked message."""
    hints: List[str] = []
    for key in reason:
        k = (key or "").strip().lower()
        # Normalize snake_case / spaces for lookup
        k_alt = k.replace(" ", "_") if k else ""
        hint = (
            BLOCKED_CATEGORY_HINTS.get(k)
            or BLOCKED_CATEGORY_HINTS.get(k_alt)
            or BLOCKED_CATEGORY_HINTS.get(key)
            or ("triggered filter: " + key if key else "policy violation")
        )
        hints.append(hint)
    return hints if hints else ["content violated our safety policy"]

try:
    from google.api_core.client_options import ClientOptions
    from google.cloud import modelarmor_v1
    MODEL_ARMOR_AVAILABLE = True
except ImportError:
    modelarmor_v1 = None
    ClientOptions = None
    MODEL_ARMOR_AVAILABLE = False


def _model_armor_location() -> str:
    """Region for Model Armor API; must match where templates exist (e.g. Cloud Run sets REGION=us-west1)."""
    return (
        (os.getenv("GCP_LOCATION") or os.getenv("REGION") or os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1")
    ).strip()


def _template_name(security_level: str) -> str | None:
    """Map security_level to full Model Armor template resource name.
    Set MODEL_ARMOR_TEMPLATE (e.g. 'test') to use a single template for both medium and high.
    """
    project_id = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
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


def _extract_sanitized_prompt(sanitization_result: Any) -> str | None:
    """If SDP deidentify was applied, return the sanitized (de-identified) prompt text; else None."""
    if not sanitization_result or not getattr(sanitization_result, "filter_results", None):
        return None
    try:
        for key, val in sanitization_result.filter_results.items():
            if not hasattr(val, "sdp_filter_result") or val.sdp_filter_result is None:
                continue
            sdp = val.sdp_filter_result
            if not getattr(sdp, "deidentify_result", None) or sdp.deidentify_result is None:
                continue
            data = getattr(sdp.deidentify_result, "data", None)
            if data is not None and hasattr(data, "text") and (data.text or "").strip():
                return data.text.strip()
    except Exception:
        pass
    return None


def _deidentify_via_dlp(text: str) -> str | None:
    """Call DLP deidentify_content with our templates; return de-identified text or None."""
    project_id = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
    location = (os.getenv("GCP_LOCATION") or "us-central1").strip()
    if not project_id or not text:
        return None
    try:
        from google.api_core.client_options import ClientOptions
        from google.cloud import dlp_v2

        parent = f"projects/{project_id}/locations/{location}"
        inspect_name = f"{parent}/inspectTemplates/identification-template"
        deid_name = f"{parent}/deidentifyTemplates/deidentify-replace-with-infotype"
        client = dlp_v2.DlpServiceClient(
            client_options=ClientOptions(api_endpoint=f"dlp.{location}.rep.googleapis.com"),
        )
        req = dlp_v2.DeidentifyContentRequest(
            parent=parent,
            item=dlp_v2.ContentItem(value=text),
            inspect_template_name=inspect_name,
            deidentify_template_name=deid_name,
        )
        resp = client.deidentify_content(request=req)
        out = getattr(resp.item, "value", None) or ""
        return out.strip() or None
    except Exception:
        return None


# FilterMatchState enum values (for when API returns int)
_FILTER_MATCH_STATE_NAMES = {0: "UNSPECIFIED", 1: "NO_MATCH_FOUND", 2: "MATCH_FOUND"}
# InvocationResult enum values
_INVOCATION_RESULT_NAMES = {0: "UNSPECIFIED", 1: "SUCCESS", 2: "PARTIAL", 3: "FAILURE"}


def _match_state_str(obj: Any) -> str:
    """Get human-readable match state from a result object (enum or direct match_state)."""
    if obj is None:
        return "—"
    # Handle raw enum int (e.g. from REST)
    if isinstance(obj, int):
        return _FILTER_MATCH_STATE_NAMES.get(obj, str(obj))
    ms = getattr(obj, "match_state", None)
    if ms is None:
        return "—"
    if isinstance(ms, int):
        return _FILTER_MATCH_STATE_NAMES.get(ms, str(ms))
    if hasattr(ms, "name"):
        name = getattr(ms, "name", "") or ""
        if name:
            return name
    s = str(ms).upper()
    if "MATCH_FOUND" in s:
        return "MATCH_FOUND"
    if "NO_MATCH" in s:
        return "NO_MATCH_FOUND"
    return s or "—"


def _filter_result_match_state(filter_result: Any) -> str:
    """Get match_state from a FilterResult (oneof: rai/sdp/pi_and_jailbreak/malicious_uri/csam/virus)."""
    if filter_result is None:
        return "—"
    # REST transport may return plain dicts that mirror the logging JSON.
    # Handle that first so any summaries we build match Cloud Logging exactly.
    if isinstance(filter_result, dict):
        # Direct match_state on this object
        if "match_state" in filter_result or "matchState" in filter_result:
            raw = filter_result.get("match_state", filter_result.get("matchState"))
            return _match_state_str(raw)
        # Nested filter-specific result (e.g. piAndJailbreakFilterResult, maliciousUriFilterResult, csamFilterFilterResult, raiFilterResult)
        for nested_key in (
            "raiFilterResult",
            "sdpFilterResult",
            "piAndJailbreakFilterResult",
            "maliciousUriFilterResult",
            "csamFilterFilterResult",
            "virusScanFilterResult",
        ):
            nested = filter_result.get(nested_key)
            if isinstance(nested, dict):
                if "match_state" in nested or "matchState" in nested:
                    raw = nested.get("match_state", nested.get("matchState"))
                    return _match_state_str(raw)
        # Fallback: look for any nested dict that has matchState/match_state
        for v in filter_result.values():
            if isinstance(v, dict) and ("match_state" in v or "matchState" in v):
                raw = v.get("match_state", v.get("matchState"))
                return _match_state_str(raw)
        # If nothing found, fall through to proto-based handling below.
    # FilterResult has oneof filter_result; only one of these is set
    for attr in (
        "rai_filter_result",
        "sdp_filter_result",
        "pi_and_jailbreak_filter_result",
        "malicious_uri_filter_result",
        "csam_filter_filter_result",
        "virus_scan_filter_result",
    ):
        nested = getattr(filter_result, attr, None)
        if nested is not None:
            # SdpFilterResult has no top-level match_state; it has inspect_result or deidentify_result (oneof)
            if attr == "sdp_filter_result":
                for sub in ("deidentify_result", "inspect_result"):
                    sub_result = getattr(nested, sub, None)
                    if sub_result is not None:
                        return _match_state_str(sub_result)
                return "—"
            return _match_state_str(nested)
    return "—"


def _build_armor_response_summary(sanitization_result: Any) -> tuple[str, str]:
    """
    Build a short glimpse and full-details string from Model Armor sanitization_result.
    Returns (glimpse, full_details) for logging.
    """
    if not sanitization_result:
        return ("—", "No sanitization result.")
    glimpse_parts: List[str] = []
    full_lines: List[str] = []

    # Overall state (filter_match_state can be enum or int from REST)
    filter_match_state = getattr(sanitization_result, "filter_match_state", None)
    overall = _match_state_str(filter_match_state)
    full_lines.append(f"Overall: {overall}")

    invocation_result = getattr(sanitization_result, "invocation_result", None)
    inv_val = invocation_result if isinstance(invocation_result, int) else getattr(invocation_result, "value", None)
    if invocation_result is not None:
        if isinstance(invocation_result, int):
            inv_str = _INVOCATION_RESULT_NAMES.get(invocation_result, str(invocation_result))
        else:
            inv_str = str(getattr(invocation_result, "name", invocation_result)).replace("INVOCATION_RESULT_", "")
        full_lines.append(f"Invocation: {inv_str}")
    # Note when invocation failed so SDP likely did not run (no de-identification)
    if inv_val == 3:  # INVOCATION_RESULT_FAILURE
        full_lines.append("")
        full_lines.append("Note: Invocation FAILURE — SDP filters may not have run. De-identified prompt is not available. Check template configuration and DLP permissions.")

    # Per-filter results (FilterResult is oneof; match_state is on the nested result)
    filter_results = getattr(sanitization_result, "filter_results", None) or {}
    full_lines.append("")
    full_lines.append("Filters:")
    for key, val in filter_results.items():
        state = _filter_result_match_state(val)
        glimpse_parts.append(f"{key}={state}")
        full_lines.append(f"  • {key}: {state}")
        # Optional extra detail per filter type
        if hasattr(val, "sdp_filter_result") and val.sdp_filter_result is not None:
            sdp = val.sdp_filter_result
            if getattr(sdp, "deidentify_result", None) is not None:
                dr = sdp.deidentify_result
                info_types = getattr(dr, "info_types", None) or []
                if info_types:
                    full_lines.append(f"      deidentified info_types: {', '.join(info_types)}")

    glimpse = ", ".join(glimpse_parts) if glimpse_parts else overall
    full_details = "\n".join(full_lines)
    return (glimpse, full_details)


def scan_prompt(text: str, security_level: str) -> Dict[str, Any]:
    """
    Scan user prompt with Model Armor. Returns safe=True if no threat; safe=False with reason if blocked.
    When template uses DLP (e.g. High+DLP), may return sanitized_prompt: the de-identified text to use downstream.

    Args:
        text: User prompt to scan.
        security_level: "off" | "medium" | "high". "off" skips scan.

    Returns:
        {"safe": True} or {"safe": True, "sanitized_prompt": str} or {"safe": False, "reason": [...]}.
    """
    if security_level == "off" or not security_level:
        return {"safe": True, "ran": False, "skip_reason": "security_level is off"}

    if not MODEL_ARMOR_AVAILABLE or modelarmor_v1 is None:
        return {"safe": True, "ran": False, "skip_reason": "google-cloud-modelarmor not installed"}

    template_name_val = _template_name(security_level)
    if not template_name_val:
        return {"safe": True, "ran": False, "skip_reason": "GOOGLE_CLOUD_PROJECT/GCP_PROJECT_ID not set"}

    location = _model_armor_location()
    try:
        client = modelarmor_v1.ModelArmorClient(
            transport="rest",
            client_options=ClientOptions(api_endpoint=f"modelarmor.{location}.rep.googleapis.com"),
        )
        user_prompt_data = modelarmor_v1.DataItem(text=text)
        request = modelarmor_v1.SanitizeUserPromptRequest(
            name=template_name_val,
            user_prompt_data=user_prompt_data,
        )
        response = client.sanitize_user_prompt(request=request)
    except Exception as e:
        return {"safe": True, "ran": False, "skip_reason": f"Scan error (region {location}): {str(e)[:120]}"}

    # Check sanitization_result.filter_match_state: MATCH_FOUND = threat, NO_MATCH_FOUND = safe
    sanitization_result = getattr(response, "sanitization_result", None)
    if not sanitization_result:
        return {"safe": True, "ran": True, "armor_summary": "", "armor_details": ""}

    filter_match_state = getattr(sanitization_result, "filter_match_state", None)
    match_found = (
        filter_match_state == 2
        or (hasattr(filter_match_state, "name") and getattr(filter_match_state, "name", "") == "MATCH_FOUND")
        or str(filter_match_state) == "MATCH_FOUND"
        or getattr(filter_match_state, "value", None) == 2
    )

    # Build response summary for logging (glimpse + full details)
    armor_summary, armor_details = _build_armor_response_summary(sanitization_result)
    sanitized = _extract_sanitized_prompt(sanitization_result)

    if match_found:
        reasons: List[str] = []
        try:
            if hasattr(sanitization_result, "filter_results") and sanitization_result.filter_results:
                for key, val in sanitization_result.filter_results.items():
                    state = _filter_result_match_state(val)
                    # Exact MATCH_FOUND only (avoid treating NO_MATCH_FOUND as match)
                    if state and str(state).upper() == "MATCH_FOUND":
                        reasons.append(key)
        except Exception:
            pass
        if not reasons:
            reasons = ["Model Armor filter match"]
        # SDP de-identification is not a block: when the only "match" is SDP (or unknown), pass with sanitized text
        sdp_only_or_unknown = (
            not reasons
            or set(reasons) <= {"sdp"}
            or (len(reasons) == 1 and reasons[0] == "Model Armor filter match")
        )
        if sdp_only_or_unknown and "deidentified info_types" in (armor_details or ""):
            if sanitized is None:
                sanitized = _deidentify_via_dlp(text)
            if sanitized is not None:
                out: Dict[str, Any] = {
                    "safe": True,
                    "armor_summary": armor_summary,
                    "armor_details": armor_details,
                    "sanitized_prompt": sanitized,
                }
                return out
        return {
            "safe": False,
            "ran": True,
            "reason": reasons,
            "armor_summary": armor_summary,
            "armor_details": armor_details,
        }

    # Passed: return sanitized prompt if DLP deidentified it (e.g. High+DLP template)
    out: Dict[str, Any] = {
        "safe": True,
        "ran": True,
        "armor_summary": armor_summary,
        "armor_details": armor_details,
    }
    if sanitized is not None:
        out["sanitized_prompt"] = sanitized
    return out
