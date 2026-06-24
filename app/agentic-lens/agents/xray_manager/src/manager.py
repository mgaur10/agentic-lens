        """
        X-Ray Manager — Advisory IAM analysis (single-shot, no code validation).

        Single-shot pipeline: uses xray_architect, xray_specialist, xray_auditor.
        """
        import logging
        import os
        from typing import Optional

        logger = logging.getLogger(__name__)


        def _call_engine(engine_id: str, message: str, session_id: str = "xray_session") -> str:
            """Call a peer Reasoning Engine."""
            if not engine_id:
                return "[Engine not configured for this QA environment]"
            try:
                from vertexai.agent_engines import ReasoningEngine
                engine = ReasoningEngine(engine_id)
                return engine.query(message=message, session_id=session_id)
            except Exception as e:
                logger.error(f"Engine call error: {e}")
                return f"Error: {e}"


        def audit_iam(
            resource_description: str,
            project: Optional[str] = None,
            location: Optional[str] = None,
        ) -> str:
            """
            Run the X-Ray IAM audit pipeline.

            Args:
                resource_description: Description of the resource or request to audit.
                project: GCP project ID (optional, uses env if not provided).
                location: GCP location (optional).

            Returns:
                str: Complete IAM audit report.
            """
            architect_id = os.environ.get("AGENTIC_LENS_ENGINE_XRAY_ARCHITECT", "")
            specialist_id = os.environ.get("AGENTIC_LENS_ENGINE_XRAY_SPECIALIST", "")
            auditor_id = os.environ.get("AGENTIC_LENS_ENGINE_XRAY_AUDITOR", "")

            proj = project or os.environ.get("GCP_PROJECT_ID", "")
            loc = location or os.environ.get("GCP_LOCATION", "us-central1")

            query = resource_description
            if proj:
                query = f"Project: {proj}\nLocation: {loc}\n\n{resource_description}"

            logger.info(f"[xray_manager] Starting audit pipeline for: {query[:100]}")

            # Step 1: Architect — IAM structure analysis
            arch_result = _call_engine(architect_id, query)

            # Step 2: Specialist — Detailed IAM check
            spec_prompt = f"Analyze this IAM configuration in detail:\n{arch_result}\n\nOriginal request: {query}"
            spec_result = _call_engine(specialist_id, spec_prompt)

            # Step 3: Auditor — Independent verification
            audit_prompt = (
                f"Verify and validate this security analysis:\n\n"
                f"ARCHITECT ANALYSIS:\n{arch_result}\n\n"
                f"SPECIALIST ANALYSIS:\n{spec_result}\n\n"
                f"Original request: {query}"
            )
            audit_result = _call_engine(auditor_id, audit_prompt)

            return f"""## X-Ray Security Audit Report

### Architecture Analysis
{arch_result}

### Specialist Analysis
{spec_result}

### Audit Verification
{audit_result}
"""
