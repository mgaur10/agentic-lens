"""
Agentic-Prism Supervisor — reasoning engine logic.
Step A: Security gate (Model Armor).
Step B: Routing (Gemini 2.5) with strict heuristic pre-checks.
"""

import logging
import os
import json
import re
import contextvars
from typing import Any
try:
    from opentelemetry.trace import Status, StatusCode
except Exception:
    class StatusCode:
        ERROR = "ERROR"

    class Status:
        def __init__(self, _code):
            self.code = _code

try:
    from .telemetry import get_tracer
except (ImportError, ValueError):
    from telemetry import get_tracer

try:
    from .model_armor_client import ModelArmorClient
except (ImportError, ValueError):
    try:
        from model_armor_client import ModelArmorClient
    except ImportError:
        ModelArmorClient = None

logger = logging.getLogger(__name__)
tracer = get_tracer()

# ---------------------------------------------------------------------------
# 1. COMPETITOR INTERCEPTION (Highest Priority)
# ---------------------------------------------------------------------------
COMPETITOR_KEYWORDS = [
    "aws", "amazon", "azure", "microsoft", "openai", "chatgpt", "s3",
    "copilot", "bedrock", "anthropic", "claude"
]

# ---------------------------------------------------------------------------
# 2. SEMANTIC TIE-BREAKERS (Regex Rules)
# ---------------------------------------------------------------------------
# Pattern: Action Verb + Repo -> Eng
REPO_DEPLOY_PATTERN = re.compile(r"(deploy|build|provision|create|launch).*(repo|github|code)", re.IGNORECASE)
# Pattern: Audit Verb + Repo -> X-Ray
REPO_AUDIT_PATTERN = re.compile(r"(check|audit|analyze|scan|review|read|what is in).*(repo|github|code)", re.IGNORECASE)

# Pattern: Deployment Verb + Security Noun -> X-Ray (The "Info over Action" Rule)
# Example: "What permissions (Noun) do I need to deploy (Verb)?"
SECURITY_NOUNS = r"(permissions?|iam|roles?|access|policy|policies|privilege|service account)"
DEPLOYMENT_VERBS = r"(deploy|build|provision|run|execute)"
SEMANTIC_PRIORITY_PATTERN = re.compile(f"({DEPLOYMENT_VERBS}.*{SECURITY_NOUNS})|({SECURITY_NOUNS}.*{DEPLOYMENT_VERBS})", re.IGNORECASE)

# Pattern: Code Generation -> Eng (Explicit "Write Code" requests)
# Example: "Write a python script", "Generate Terraform"
CODE_GENERATION_PATTERN = re.compile(r"(write|generate|create|draft).*(script|code|python|terraform|yaml|json|function|class)", re.IGNORECASE)

# Pattern: 403/Forbidden error explanation -> X-Ray (Explain 403s; not deployment fix)
# Example: "My Cloud Run is failing with 403 when calling Pub/Sub. Why?"
ERROR_403_EXPLAIN_PATTERN = re.compile(
    r"(403|forbidden|permission denied).*(why|failing|error|when calling)",
    re.IGNORECASE
)

# GCP solution architecture / service selection (not security-audit intent) -> Eng
GCP_CONTEXT = r"(?:google\s+cloud|\bgcp\b)"
GCP_ARCHITECTURE_PATTERN = re.compile(
    rf"{GCP_CONTEXT}.{{0,400}}(?:architecture|reference\s+architecture|serverless|highly\s+available|"
    r"solution\s+architecture|multi[-\s]?service|which\s+.{{0,48}}service|what\s+.{{0,48}}service|"
    r"list\s+.{{0,72}}services|specific\s+.{{0,32}}gcp|services\s+i\s+should\s+use|"
    r"services\s+to\s+use)|"
    rf"(?:architecture|reference\s+architecture|serverless|highly\s+available|"
    r"solution\s+architecture|e[-\s]?commerce).{{0,220}}{GCP_CONTEXT}",
    re.IGNORECASE | re.DOTALL,
)

# Compare two or more Google Cloud runtimes / platforms -> Eng
GCP_PRODUCT_COMPARE_PATTERN = re.compile(
    r"(?:\bcompare\b|\bversus\b|\s+vs\.?\s).{0,240}?"
    r"(?:cloud\s+run|gke|kubernetes\s+engine|autopilot|compute\s+engine|"
    r"app\s+engine|cloud\s+functions|vertex\s+ai)|"
    r"(?:cloud\s+run).{0,160}(?:gke|autopilot|kubernetes)|"
    r"(?:gke|autopilot|kubernetes).{0,160}(?:cloud\s+run)",
    re.IGNORECASE | re.DOTALL,
)

LENS_TRACEPARENT_MARKER_RE = re.compile(r"^\s*<!--\s*LENS_TRACEPARENT:[^>]+-->\s*\n?", re.IGNORECASE)
LENS_TRACESTATE_MARKER_RE = re.compile(r"^\s*<!--\s*LENS_TRACESTATE:[^>]+-->\s*\n?", re.IGNORECASE)
_LENS_TP_VALUE_RE = re.compile(r"^\s*<!--\s*LENS_TRACEPARENT:([^>]+?)-->\s*\n?", re.IGNORECASE)
_LENS_TS_VALUE_RE = re.compile(r"^\s*<!--\s*LENS_TRACESTATE:([^>]+?)-->\s*\n?", re.IGNORECASE)
# Correlates with Glass UI /api/query (stripped before Model Armor and LLM).
_LENS_REQUEST_ID_MARKER_RE = re.compile(
    r"^\s*<!--\s*LENS_REQUEST_ID:([^>]+?)\s*-->\s*\n?",
    re.IGNORECASE,
)
_lens_request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "lens_request_id", default=None
)


def _extract_lens_request_id_line(message: str) -> tuple[str | None, str]:
    raw = message or ""
    m = _LENS_REQUEST_ID_MARKER_RE.match(raw)
    if not m:
        return (None, raw)
    rid = (m.group(1) or "").strip() or None
    return (rid, raw[m.end() :])


def _extract_lens_w3c_comment_prefix(text: str) -> tuple[str | None, str | None, str]:
    """Remove leading LENS_TRACEPARENT / LENS_TRACESTATE HTML lines; return (tp, ts, rest)."""
    rest = text or ""
    tp = ts = None
    m = _LENS_TP_VALUE_RE.match(rest)
    if m:
        tp = (m.group(1) or "").strip() or None
        rest = rest[m.end() :]
    m = _LENS_TS_VALUE_RE.match(rest)
    if m:
        ts = (m.group(1) or "").strip() or None
        rest = rest[m.end() :]
    return (tp, ts, rest)


def get_lens_request_id_for_span() -> str | None:
    """Best-effort correlation id for OTel (set in SupervisorAgent.reason)."""
    return _lens_request_id_ctx.get()

# ---------------------------------------------------------------------------
# 3. FALLBACK KEYWORDS (Low Priority)
# Only specific technical terms. Removed generic "code/repo".
# ---------------------------------------------------------------------------
ROUTING_KEYWORDS = {
    "agentic_lens_eng_lead": [
        "terraform", "main.tf", "gke", "vpc", "cloud run", "cloud sql",
        "cloud function", "pub/sub", "memorystore", "redis", "cloudbuild",
        "artifact registry", "eventarc", "bigquery", "failing to connect",
        "autopilot", "serverless", "solution architecture", "google cloud architecture",
    ],
    "agentic_lens_events": [
        "conference", "schedule", "ticket", "speaker", "venue", "keynote",
        "session", "panel", "lunch", "registration", "badge", "workshop",
        "lab", "party", "after party"
    ],
    "agentic_lens_xray_manager": [
        "audit", "iam", "least privilege", "custom role", "service account",
        "secret manager", "org policy", "cmek", "kms", "403", "forbidden"
    ],
}

CHAT_FALLBACK = "agentic_lens_chat"

# ---------------------------------------------------------------------------
# ROUTING LOGIC
# ---------------------------------------------------------------------------

ROUTING_PROMPT = """
You are the Supervisor for Agentic-Prism. Your goal is to classify the user query into exactly one target agent.

### THE AGENTS

1. **agentic_lens_chat (The Brand Ambassador)**
   - **CRITICAL:** Handles ALL questions about **Competitors** (AWS, Azure, OpenAI, ChatGPT).
   - **Role:** Greetings, General Tech, Pivot to Google Cloud.
   - **Triggers:** "Hi", "Who are you?", "How do I use AWS?", "Compare ChatGPT vs Gemini".

2. **agentic_lens_eng_lead (The Builder)**
   - **Role:** DevOps & Infrastructure.
   - **Capabilities:** Write Terraform, Deploy GKE/Cloud Run, Fix Builds.
   - **Triggers:** "Deploy this", "Write Terraform", "Fix this error".
   - **NEGATIVE CONSTRAINT:** NEVER use for security audits or permission checks.

3. **agentic_lens_xray_manager (The Auditor)**
   - **Role:** Security & IAM.
   - **Capabilities:** Audit Permissions, Analyze Repos, Explain 403s.
   - **Triggers:** "What permissions do I need?", "Audit this repo", "Check for keys".

4. **agentic_lens_events (The Concierge)**
   - **Role:** Conference Logistics.
   - **Triggers:** "When is the keynote?", "Where is lunch?".

### ROUTING TIE-BREAKERS

1. **The "Repo" Rule:**
   - User: "Deploy this repo" -> **eng_lead**
   - User: "Audit this repo" -> **xray_manager**

2. **The "Semantic Priority" Rule:**
   - If query has BOTH "Deploy" (Verb) AND "Permissions" (Noun):
   - **PRIORITIZE X-RAY.** The user wants *information*, not action.
   - Example: "What permissions do I need to deploy?" -> **xray_manager**

3. **Architecture & product comparison (Google Cloud only):**
   - Multi-service / HA / serverless **architecture on GCP**, or **which GCP services** to use -> **eng_lead**
   - **Compare** Google Cloud products (e.g. Cloud Run vs GKE Autopilot) -> **eng_lead**

### OUTPUT FORMAT
Return JSON: {"target_agent": "<agent_name>", "forwarded_query": "<query>"}
"""

def _route_with_heuristics(query: str) -> dict[str, str] | None:
    """Deterministic rules (The 'Reflexes')."""
    q = (query or "").strip().lower()

    # 1. Competitor Check (Highest Priority)
    if any(kw in q for kw in COMPETITOR_KEYWORDS):
        return {"target_agent": CHAT_FALLBACK, "forwarded_query": query}

    # 2. Semantic Priority (Permissions > Deployment)
    if SEMANTIC_PRIORITY_PATTERN.search(q):
        logger.info("Routing: Semantic Priority Rule matched -> X-Ray")
        return {"target_agent": "agentic_lens_xray_manager", "forwarded_query": query}

    # 3. 403/Forbidden error explanation -> X-Ray (Explain 403s)
    if ERROR_403_EXPLAIN_PATTERN.search(q):
        logger.info("Routing: 403/Forbidden explanation -> X-Ray")
        return {"target_agent": "agentic_lens_xray_manager", "forwarded_query": query}

    # 3.5. Least-privilege IAM + repo/Terraform review -> X-Ray
    # This must be a reflex (deterministic) so we don't rely on Gemini routing when the prompt is clearly security audit work.
    if (
        ("github.com" in q or "repo:" in q or "repository" in q)
        and (
            ("least privilege" in q or "least-privilege" in q)
            or ("iam" in q or "permissions" in q)
        )
        and (("review" in q or "audit" in q or "analyze" in q or "scan" in q) or ("terraform" in q))
    ):
        logger.info("Routing: least-privilege IAM repo/Terraform review -> X-Ray")
        return {"target_agent": "agentic_lens_xray_manager", "forwarded_query": query}

    # 4. Repo/Code Inspection vs Deployment
    if REPO_AUDIT_PATTERN.search(q):
         return {"target_agent": "agentic_lens_xray_manager", "forwarded_query": query}

    # 5. GCP product comparison (e.g. Cloud Run vs GKE) -> Eng
    if GCP_PRODUCT_COMPARE_PATTERN.search(q):
        logger.info("Routing: GCP product comparison -> Engineering")
        return {"target_agent": "agentic_lens_eng_lead", "forwarded_query": query}

    # 6. GCP architecture / service selection -> Eng
    if GCP_ARCHITECTURE_PATTERN.search(q):
        logger.info("Routing: GCP architecture / service selection -> Engineering")
        return {"target_agent": "agentic_lens_eng_lead", "forwarded_query": query}

    # 7. Code Generation (Explicit "Write" requests -> Eng)
    if CODE_GENERATION_PATTERN.search(q):
         return {"target_agent": "agentic_lens_eng_lead", "forwarded_query": query}

    if REPO_DEPLOY_PATTERN.search(q):
         return {"target_agent": "agentic_lens_eng_lead", "forwarded_query": query}

    return None

def _route_with_keywords(query: str) -> dict[str, str]:
    """Fallback keyword matching. X-Ray before eng_lead when IAM/error intent (403, forbidden)."""
    q = query.lower()
    # Prefer X-Ray for 403/forbidden/audit intent so "403 when calling Pub/Sub" -> xray_manager
    xray_kw = ROUTING_KEYWORDS.get("agentic_lens_xray_manager", [])
    if any(kw in q for kw in xray_kw):
        return {"target_agent": "agentic_lens_xray_manager", "forwarded_query": query}
    for agent, keywords in ROUTING_KEYWORDS.items():
        if agent == "agentic_lens_xray_manager":
            continue
        if any(kw in q for kw in keywords):
            return {"target_agent": agent, "forwarded_query": query}
    return {"target_agent": CHAT_FALLBACK, "forwarded_query": query}

def _route_with_gemini(user_query: str) -> dict[str, str]:
    """LLM Classification."""
    with tracer.start_as_current_span("lens.supervisor.route_with_gemini") as span:
        span.set_attribute("agent.system", "agentic_lens")
        span.set_attribute("department", "supervisor")
        span.set_attribute("agent.role", "supervisor")
        _rid = get_lens_request_id_for_span()
        if _rid:
            span.set_attribute("lens.request_id", _rid)

        # 1. Run Heuristics First (The "Reflexes")
        reflex = _route_with_heuristics(user_query)
        if reflex:
            span.set_attribute("routing.mode", "heuristic")
            span.set_attribute("routing.target_agent", reflex.get("target_agent", CHAT_FALLBACK))
            return reflex

        # 2. Run LLM (The "Brain")
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel

            project_id = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
            location = (os.getenv("GCP_LOCATION") or os.getenv("REGION") or "us-central1").strip()

            if not project_id:
                fallback = _route_with_keywords(user_query)
                span.set_attribute("routing.mode", "keyword_fallback_no_project")
                span.set_attribute("routing.target_agent", fallback.get("target_agent", CHAT_FALLBACK))
                return fallback

            from vertex_init import init_vertexai as _init_vertex

            _init_vertex(project_id, location)
            model = GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(
                f"{ROUTING_PROMPT}\n\nUser query: {user_query}",
                generation_config={"temperature": 0.0, "response_mime_type": "application/json"},
            )

            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            data = json.loads(text)
            out = {"target_agent": data.get("target_agent", CHAT_FALLBACK), "forwarded_query": user_query}
            span.set_attribute("routing.mode", "gemini")
            span.set_attribute("routing.target_agent", out["target_agent"])
            return out

        except Exception as e:
            logger.error(f"Routing Error: {e}")
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR))
            fallback = _route_with_keywords(user_query)
            span.set_attribute("routing.mode", "keyword_fallback_error")
            span.set_attribute("routing.target_agent", fallback.get("target_agent", CHAT_FALLBACK))
            return fallback


class SupervisorAgent:
    """
    Supervisor agent: security gate (Model Armor) then routing (Gemini 2.5).
    """
    def __init__(self, model_armor_client: ModelArmorClient | None = None):
        self._model_armor_client = model_armor_client or ModelArmorClient()

    def reason(
        self,
        user_query: str,
        security_level: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Step A: Security Gate (Model Armor) -> BLOCK or PASS
        Step B: Routing (Gemini 2.5) -> target_agent
        """
        # Strip hidden Lens markers before policy/routing / LLM (never treat as user text).
        q = user_query or ""
        lens_rid, q = _extract_lens_request_id_line(q)
        tp, ts, q = _extract_lens_w3c_comment_prefix(q)
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
            except Exception:
                remote_ctx = None

        rid_token = None
        if lens_rid:
            rid_token = _lens_request_id_ctx.set(lens_rid)
        try:
            with tracer.start_as_current_span("lens.supervisor.reason", context=remote_ctx) as span:
                span.set_attribute("agent.system", "agentic_lens")
                span.set_attribute("department", "supervisor")
                span.set_attribute("agent.role", "supervisor")
                span.set_attribute("security.level", security_level or "off")
                if lens_rid:
                    span.set_attribute("lens.request_id", lens_rid)

                query_after_security = q

                if security_level and security_level.strip().lower() != "off":
                    result = self._model_armor_client.sanitize(
                        q, security_level.strip().lower()
                    )
                    if result.get("block"):
                        logger.warning("🛡️ Security Violation Detected")
                        span.set_attribute("security.blocked", True)
                        return {
                            "agent": "BLOCK",
                            "response": "Request blocked by Security Policy.",
                        }
                    query_after_security = result.get("sanitized_prompt") or q
                    span.set_attribute("security.blocked", False)

                routing_result = _route_with_gemini(query_after_security)
                target_agent = routing_result.get("target_agent", "agentic_lens_chat")
                forwarded_query = routing_result.get("forwarded_query", query_after_security)
                span.set_attribute("routing.target_agent", target_agent)

                out: dict[str, Any] = {
                    "agent": target_agent,
                    "target_agent": target_agent,
                    "forwarded_query": forwarded_query,
                }
                if session_id is not None and session_id != "":
                    out["session_id"] = session_id
                return out
        finally:
            if rid_token is not None:
                _lens_request_id_ctx.reset(rid_token)


def reason(
    user_query: str,
    security_level: str,
    session_id: str | None = None,
    model_armor_client: ModelArmorClient | None = None,
) -> dict[str, Any]:
    """
    Supervisor reasoning: security gate → routing → dispatch.
    Delegates to SupervisorAgent.reason().
    """
    agent = SupervisorAgent(model_armor_client=model_armor_client)
    return agent.reason(user_query, security_level, session_id)
