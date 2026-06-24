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
            from src.model_armor_client import ModelArmorClient
        except ImportError:
            from model_armor_client import ModelArmorClient

        logger = logging.getLogger(__name__)

        # ── Heuristic patterns ─────────────────────────────────────────────────────
        COMPETITOR_KEYWORDS = re.compile(
            r'\b(aws|azure|openai|chatgpt|anthropic|gpt-4|gpt4|claude|mistral|llama)\b',
            re.IGNORECASE,
        )
        REPO_DEPLOY_PATTERN = re.compile(
            r'(deploy|build|provision|create|launch).*(repo|github|code)', re.IGNORECASE
        )
        REPO_AUDIT_PATTERN = re.compile(
            r'(check|audit|analyze|scan|review|read|what is in).*(repo|github|code)', re.IGNORECASE
        )
        SECURITY_NOUNS = re.compile(
            r'(permissions?|iam|roles?|access|policy|policies|privilege|service account)',
            re.IGNORECASE,
        )
        DEPLOYMENT_VERBS = re.compile(
            r'(deploy|build|provision|run|execute)', re.IGNORECASE
        )
        SEMANTIC_PRIORITY_PATTERN = re.compile(
            r'(deploy|build|provision|run|execute).*(permissions?|iam|roles?|access|policy|policies|privilege|service account)', re.IGNORECASE
        )
        CODE_GENERATION_PATTERN = re.compile(
            r'(write|generate|create|draft).*(script|code|python|terraform|yaml|json|function|class)',
            re.IGNORECASE,
        )
        ERROR_403_EXPLAIN_PATTERN = re.compile(
            r'(403|forbidden|permission denied).*(why|failing|error|when calling)',
            re.IGNORECASE,
        )
        ROUTING_KEYWORDS = {
            "agentic_prism_chat": ["hi", "hello", "who are you", "what is", "compare", "competitor"],
        }
        CHAT_FALLBACK = "agentic_prism_chat"

        ROUTING_PROMPT = """
You are the Supervisor for Agentic-Prism. Your goal is to classify the user query into exactly one target agent.

### THE AGENTS

1. **agentic_prism_chat (The Brand Ambassador)**
   - **CRITICAL:** Handles ALL questions about **Competitors** (AWS, Azure, OpenAI, ChatGPT).
   - **Role:** Greetings, General Tech, Pivot to Google Cloud.
   - **Triggers:** "Hi", "Who are you?", "How do I use AWS?", "Compare ChatGPT vs Gemini".

2. **agentic_prism_eng_lead (The Builder)**
   - **Role:** DevOps & Infrastructure.
   - **Capabilities:** Write Terraform, Deploy GKE/Cloud Run, Fix Builds.
   - **Triggers:** "Deploy this", "Write Terraform", "Fix this error".
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

        def _route_with_heuristics(query: str) -> str | None:
            """Fast heuristic routing. Returns agent name or None."""
            q = query.lower()
            if COMPETITOR_KEYWORDS.search(q):
                return CHAT_FALLBACK
            if REPO_AUDIT_PATTERN.search(q):
                return "agentic_prism_xray_manager"
            if REPO_DEPLOY_PATTERN.search(q):
                return "agentic_prism_eng_lead"
            has_sec = bool(SECURITY_NOUNS.search(q))
            has_dep = bool(DEPLOYMENT_VERBS.search(q))
            if has_sec and has_dep:
                return "agentic_prism_xray_manager"
            if ERROR_403_EXPLAIN_PATTERN.search(q):
                return "agentic_prism_xray_manager"
            if CODE_GENERATION_PATTERN.search(q):
                return "agentic_prism_eng_lead"
            return None

        def _route_with_keywords(query: str) -> str | None:
            """Keyword-based routing for simple cases."""
            q = query.lower()
            for agent, keywords in ROUTING_KEYWORDS.items():
                if any(kw in q for kw in keywords):
                    return agent
            return None

        def _route_with_gemini(query: str, model_client: Any) -> str:
            """LLM-based routing as fallback."""
            try:
                from google import genai
                response = model_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=ROUTING_PROMPT + f"\n\nUser query: {query}",
                )
                text = response.text.strip()
                # Parse JSON from response
                m = re.search(r'\{.*\}', text, re.DOTALL)
                if m:
                    result = json.loads(m.group())
                    return result.get("target_agent", CHAT_FALLBACK)
            except Exception as e:
                logger.warning(f"LLM routing failed: {e}")
            return CHAT_FALLBACK


        class SupervisorAgent:
            """Agentic-Prism Supervisor — routes queries to specialist agents."""

            def __init__(self):
                self._armor = ModelArmorClient()
                self._peer_engines: dict[str, str] = {}
                self._load_peer_engines()

            def _load_peer_engines(self):
                """Load peer engine resource names from environment variables."""
                env_map = {
                    "agentic_prism_eng_lead": os.environ.get("AGENTIC_LENS_ENGINE_ENG_LEAD", ""),
                    "agentic_prism_xray_manager": os.environ.get("AGENTIC_LENS_ENGINE_XRAY_MANAGER", ""),
                    "agentic_prism_events": os.environ.get("AGENTIC_LENS_ENGINE_EVENTS", ""),
                    "agentic_prism_chat": os.environ.get("CHAT_ENGINE_ID", ""),
                }
                self._peer_engines = {k: v for k, v in env_map.items() if v}
                logger.info(f"[supervisor] Loaded {len(self._peer_engines)} peer engines")

            def reason(self, *, message: str, session_id: str | None = None) -> str:
                """Main entry point — security gate + route + forward."""
                # Step A: Security gate
                guard = self._armor.sanitize(message)
                if guard.get("action") == "BLOCK":
                    return "I'm sorry, I cannot process that request."

                # Step B: Routing
                target = _route_with_heuristics(message) or _route_with_keywords(message)
                if not target:
                    target = CHAT_FALLBACK

                # Step C: Forward to peer engine
                engine_id = self._peer_engines.get(target)
                if not engine_id:
                    logger.warning(f"No engine ID for target={target}; falling back to chat")
                    target = CHAT_FALLBACK
                    engine_id = self._peer_engines.get(CHAT_FALLBACK, "")

                if not engine_id:
                    return f"[Supervisor] Routing to {target} (no engine configured in QA)"

                try:
                    from google.cloud import aiplatform
                    from vertexai.agent_engines import ReasoningEngine
                    engine = ReasoningEngine(engine_id)
                    result = engine.query(message=message, session_id=session_id or "default")
                    return result
                except Exception as e:
                    logger.error(f"Peer call failed: {e}")
                    return f"[Supervisor → {target}] Error: {e}"


        # Module-level entry point used by agent.py
        _supervisor = SupervisorAgent()

        from google.adk.agents import LlmAgent
        try:
            from src.lens_llm_usage import emit_llm_usage_from_response
        except ImportError:
            from lens_llm_usage import emit_llm_usage_from_response

        def _supervisor_llm_usage_callback(callback_context, llm_response):
            """Emit structured llm_usage event to Cloud Logging (jsonPayload) after each LLM call."""
            try:
                emit_llm_usage_from_response(
                    llm_response,
                    agent_id="agentic_lens_supervisor",
                    department="supervisor",
                    agent_role="supervisor",
                )
            except Exception:
                pass
            return None  # do not modify the response

        reason = LlmAgent(
            name="agentic_prism_supervisor",
            model="gemini-2.5-flash",
            description="Supervisor that routes user queries to specialist agents after security gate.",
            instruction=ROUTING_PROMPT,
            after_model_callback=_supervisor_llm_usage_callback,
        )
