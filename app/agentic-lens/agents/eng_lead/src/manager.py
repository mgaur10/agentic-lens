        """
        Engineering Lead — orchestration logic for Scout -> Coder -> Sentinel.
        Implements orchestrate_build(user_query) -> validated code result.
        """
        import json
        import logging
        import os
        import re
        from typing import Optional

        logger = logging.getLogger(__name__)


        def _call_engine(engine_id: str, message: str) -> str:
            """Call a Vertex AI Reasoning Engine with a message."""
            if not engine_id:
                return f"[Engine not configured for this QA environment]"
            try:
                from vertexai.agent_engines import ReasoningEngine
                engine = ReasoningEngine(engine_id)
                return engine.query(message=message, session_id="eng_lead_session")
            except Exception as e:
                logger.error(f"Engine call failed: {e}")
                return f"Error calling engine: {e}"


        def orchestrate_build(user_query: str) -> str:
            """
            Orchestrate the Scout -> Coder -> Sentinel pipeline.

            Args:
                user_query: The user's infrastructure/code request.

            Returns:
                str: The final validated code or error message.
            """
            scout_id = os.environ.get("AGENTIC_LENS_ENGINE_SCOUT", "")
            coder_id = os.environ.get("AGENTIC_LENS_ENGINE_CODER", "")
            sentinel_id = os.environ.get("AGENTIC_LENS_ENGINE_SENTINEL", "")

            logger.info(f"[eng_lead] Starting orchestrate_build for: {user_query[:100]}")

            # Step 1: Scout — Infrastructure Plan
            logger.info("[eng_lead] Step 1: Scout (infrastructure plan)")
            plan = _call_engine(scout_id, user_query)

            # Step 2: Coder — Implementation
            coder_prompt = f"""Based on this infrastructure plan, write the complete implementation:

PLAN:
{plan}

ORIGINAL REQUEST: {user_query}

Write complete, working Terraform/code. Include all necessary files.""".strip()

            logger.info("[eng_lead] Step 2: Coder (implementation)")
            code = _call_engine(coder_id, coder_prompt)

            # Step 3: Sentinel — Quality & Security Review
            sentinel_prompt = f"""Review this implementation for quality and security:

IMPLEMENTATION:
{code}

Verify:
1. Security best practices (IAM least privilege, no hardcoded secrets)
2. Code quality and completeness
3. Correct GCP resource configuration

If approved, respond with: ✅ Approved
If changes needed, list specific issues.""".strip()

            logger.info("[eng_lead] Step 3: Sentinel (QA review)")
            review = _call_engine(sentinel_id, sentinel_prompt)

            # Compile result
            result = f"""## Infrastructure Implementation

### Plan (Scout)
{plan}

### Implementation (Coder)
{code}

### Quality & Security Review (Sentinel)
{review}
"""
            return result
