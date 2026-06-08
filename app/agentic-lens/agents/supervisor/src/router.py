"""
Agentic-Prism Supervisor — reasoning engine logic.
Step A: Security gate (Model Armor).
Step B: Routing (Gemini 2.5) with strict heuristic pre-checks.
"""

import logging
import os
import json
import re
from typing import Any

try:
    from .model_armor_client import ModelArmorClient
except (ImportError, ValueError):
    try:
        from model_armor_client import ModelArmorClient
    except ImportError:
        ModelArmorClient = None

logger = logging.getLogger(__name__)

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

# Pattern: GCP Architecture / Design / Comparison -> Eng
# Example: "Compare Cloud Run and GKE Autopilot", "Design a serverless e-commerce architecture on Google Cloud"
GCP_COMPUTE_SERVICES = r"(cloud run|gke|kubernetes|app engine|compute engine|cloud functions?|cloud sql|spanner|memorystore|redis|bigquery|pub/sub|vpc|gcp|google cloud)"
ENG_DESIGN_COMPARE_PATTERN = re.compile(
    rf"(design|architecture|compare|comparison|scenarios|choose|choice|difference between|how to structure).*{GCP_COMPUTE_SERVICES}|"
    rf"{GCP_COMPUTE_SERVICES}.*(design|architecture|compare|comparison|scenarios|choose|choice|difference between|how to structure)",
    re.IGNORECASE
)
ENG_DESIGN_COMPARE_EXCLUDE_KEYWORDS = ["audit", "iam", "permission", "least privilege", "service account", "key", "secret", "403", "forbidden"]

# ---------------------------------------------------------------------------
# 3. FALLBACK KEYWORDS (Low Priority)
# Only specific technical terms. Removed generic "code/repo".
# ---------------------------------------------------------------------------
ROUTING_KEYWORDS = {
    "agentic_prism_eng_lead": [
        "terraform", "main.tf", "gke", "vpc", "cloud run", "cloud sql",
        "cloud function", "pub/sub", "memorystore", "redis", "cloudbuild",
        "artifact registry", "eventarc", "bigquery", "failing to connect"
    ],
    "agentic_prism_events": [
        "conference", "schedule", "ticket", "speaker", "venue", "keynote",
        "session", "panel", "lunch", "registration", "badge", "workshop",
        "lab", "party", "after party"
    ],
    "agentic_prism_xray_manager": [
        "audit", "iam", "least privilege", "custom role", "service account",
        "secret manager", "org policy", "cmek", "kms", "403", "forbidden"
    ],
}

CHAT_FALLBACK = "agentic_prism_chat"

# ---------------------------------------------------------------------------
# ROUTING LOGIC
# ---------------------------------------------------------------------------

ROUTING_PROMPT = """
You are the Supervisor for Agentic-Prism. Your goal is to classify the user query into exactly one target agent.

### THE AGENTS

1. **agentic_prism_chat (The Brand Ambassador)**
   - **CRITICAL:** Handles ALL questions about **Competitors** (AWS, Azure, OpenAI, ChatGPT).
   - **Role:** Greetings, General Tech (excluding Google Cloud architecture/infrastructure design), Pivot to Google Cloud.
   - **Triggers:** "Hi", "Who are you?", "How do I use AWS?", "Compare ChatGPT vs Gemini".

2. **agentic_prism_eng_lead (The Builder & Architect)**
   - **Role:** DevOps, Infrastructure & Architecture.
   - **Capabilities:** Write Terraform, Deploy GKE/Cloud Run, Fix Builds, Compare GCP services, Design architectures.
   - **Triggers:** "Deploy this", "Write Terraform", "Fix this error", "Compare Cloud Run and GKE", "Design a serverless architecture".
   - **NEGATIVE CONSTRAINT:** NEVER use for security audits or permission checks.

3. **agentic_prism_xray_manager (The Auditor)**
   - **Role:** Security & IAM.
   - **Capabilities:** Audit Permissions, Analyze Repos, Explain 403s.
   - **Triggers:** "What permissions do I need?", "Audit this repo", "Check for keys".

4. **agentic_prism_events (The Concierge)**
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
        return {"target_agent": "agentic_prism_xray_manager", "forwarded_query": query}

    # 3. 403/Forbidden error explanation -> X-Ray (Explain 403s)
    if ERROR_403_EXPLAIN_PATTERN.search(q):
        logger.info("Routing: 403/Forbidden explanation -> X-Ray")
        return {"target_agent": "agentic_prism_xray_manager", "forwarded_query": query}

    # 4. Repo/Code Inspection vs Deployment
    if REPO_AUDIT_PATTERN.search(q):
         return {"target_agent": "agentic_prism_xray_manager", "forwarded_query": query}
    
    # 5. Code Generation (Explicit "Write" requests -> Eng)
    if CODE_GENERATION_PATTERN.search(q):
         return {"target_agent": "agentic_prism_eng_lead", "forwarded_query": query}

    if REPO_DEPLOY_PATTERN.search(q):
         return {"target_agent": "agentic_prism_eng_lead", "forwarded_query": query}

    # 6. GCP Architecture / Design / Comparison -> Eng
    if ENG_DESIGN_COMPARE_PATTERN.search(q):
        if not any(kw in q for kw in ENG_DESIGN_COMPARE_EXCLUDE_KEYWORDS):
             return {"target_agent": "agentic_prism_eng_lead", "forwarded_query": query}

    return None

def _route_with_keywords(query: str) -> dict[str, str]:
    """Fallback keyword matching. X-Ray before eng_lead when IAM/error intent (403, forbidden)."""
    q = query.lower()
    # Prefer X-Ray for 403/forbidden/audit intent so "403 when calling Pub/Sub" -> xray_manager
    xray_kw = ROUTING_KEYWORDS.get("agentic_prism_xray_manager", [])
    if any(kw in q for kw in xray_kw):
        return {"target_agent": "agentic_prism_xray_manager", "forwarded_query": query}
    for agent, keywords in ROUTING_KEYWORDS.items():
        if agent == "agentic_prism_xray_manager":
            continue
        if any(kw in q for kw in keywords):
            return {"target_agent": agent, "forwarded_query": query}
    return {"target_agent": CHAT_FALLBACK, "forwarded_query": query}

def _route_with_gemini(user_query: str) -> dict[str, str]:
    """LLM Classification."""
    
    # 1. Run Heuristics First (The "Reflexes")
    reflex = _route_with_heuristics(user_query)
    if reflex:
        return reflex

    # 2. Run LLM (The "Brain")
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel
        
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
        location = (os.getenv("GCP_LOCATION") or os.getenv("REGION") or "us-central1").strip()
        
        if not project_id:
            return _route_with_keywords(user_query)

        vertexai.init(project=project_id, location=location)
        model = GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            f"{ROUTING_PROMPT}\n\nUser query: {user_query}",
            generation_config={"temperature": 0.0, "response_mime_type": "application/json"},
        )
        
        try:
            from .lens_llm_usage import emit_llm_usage_from_response
        except ImportError:
            from lens_llm_usage import emit_llm_usage_from_response

        emit_llm_usage_from_response(
            response,
            agent_id="agentic_lens_supervisor",
            department="supervisor",
            agent_role="supervisor",
            model="gemini-2.5-flash",
            lens_request_id=None,
        )
        
        text = response.text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        
        data = json.loads(text)
        return {"target_agent": data.get("target_agent", CHAT_FALLBACK), "forwarded_query": user_query}

    except Exception as e:
        logger.error(f"Routing Error: {e}")
        return _route_with_keywords(user_query)


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
        # Step A: Security Gate (Model Armor)
        query_after_security = user_query
        
        if security_level and security_level.strip().lower() != "off":
            result = self._model_armor_client.sanitize(
                user_query, security_level.strip().lower()
            )
            if result.get("block"):
                logger.warning("🛡️ Security Violation Detected")
                return {
                    "agent": "BLOCK",
                    "response": "Request blocked by Security Policy.",
                }
            query_after_security = result.get("sanitized_prompt") or user_query

        # Step B: Routing (Gemini 2.5)
        routing_result = _route_with_gemini(query_after_security)
        
        target_agent = routing_result.get("target_agent", "agentic_prism_chat")
        forwarded_query = routing_result.get("forwarded_query", query_after_security)

        # Dispatch
        out: dict[str, Any] = {
            "agent": target_agent,
            "target_agent": target_agent,
            "forwarded_query": forwarded_query,
        }
        if session_id is not None and session_id != "":
            out["session_id"] = session_id
        return out


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
