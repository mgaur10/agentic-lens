"""
Engineering Pipeline - Chain of Thought Workflow
Scout (Search) -> Coder (Generate) -> Sentinel (Validate)
Now using Vertex AI (Gemini 2.0 Flash) with Google Search Grounding for real intelligence.
"""

import os
import re
import time
from typing import Callable, Dict, Optional, Tuple

from dotenv import load_dotenv
import vertexai

# GenerativeModel and Tool will be imported lazily when needed
GenerativeModel = None
Tool = None

from backend import memory, feedback

# Load environment variables
load_dotenv()

# Initialize Vertex AI; prefer GCP_PROJECT_ID (string id) over GOOGLE_CLOUD_PROJECT.
project_id = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
location = (os.getenv("GCP_LOCATION") or os.getenv("REGION") or "us-central1").strip()

if project_id:
    try:
        vertexai.init(project=project_id, location=location)
        VERTEX_AI_AVAILABLE = True
    except Exception as e:
        print(f"⚠️  Vertex AI initialization failed: {e}")
        print("   Falling back to mock mode. Run 'python manage_gcp.py' to configure.")
        VERTEX_AI_AVAILABLE = False
else:
    print("⚠️  GCP_PROJECT_ID / GOOGLE_CLOUD_PROJECT not found.")
    print("   Falling back to mock mode. Run 'python manage_gcp.py' to configure.")
    VERTEX_AI_AVAILABLE = False


class EngineeringPipeline:
    """
    Engineering Department Pipeline implementing Chain of Thought workflow.
    
    Workflow:
    1. Scout: Analyzes request and gathers requirements using Vertex AI Grounding with Google Search
    2. Coder: Generates Terraform configuration (using Vertex AI)
    3. Sentinel: Validates code for security vulnerabilities (using Vertex AI)
    
    Log Color: 🟢 Green (Google Green #34A853)
    """
    
    def __init__(self, log_callback: Optional[Callable[[str, str, int, str], None]] = None):
        """
        Initialize the Engineering Pipeline.
        
        Args:
            log_callback: Optional function to call for logging (message, log_type, turn, user_input)
        """
        self.log_callback = log_callback
        self.conversation_turn = 0
        self.user_input = ""
        self.model = None
        self.search_tool = None
        
        # Initialize memory database
        memory.init_db()
        
        # Initialize Vertex AI model
        if VERTEX_AI_AVAILABLE:
            try:
                # Lazy import with fallback for different package versions
                global GenerativeModel, Tool
                if GenerativeModel is None:
                    try:
                        # Try google.genai first (newer versions use this)
                        from google.genai import GenerativeModel
                        # Tool handling for google.genai
                        try:
                            from google.genai.types import Tool
                        except ImportError:
                            # Create a simple Tool wrapper
                            class ToolWrapper:
                                @staticmethod
                                def from_dict(d):
                                    return d
                            Tool = ToolWrapper
                    except (ImportError, AttributeError):
                        try:
                            # Try the standard vertexai import
                            from vertexai.generative_models import GenerativeModel, Tool
                        except (ImportError, AttributeError):
                            try:
                                # Try preview import
                                from vertexai.preview.generative_models import GenerativeModel, Tool
                            except (ImportError, AttributeError):
                                try:
                                    # Try google.generativeai (alternative SDK)
                                    from google.generativeai import GenerativeModel
                                    Tool = type('Tool', (), {'from_dict': lambda x: x})
                                except (ImportError, AttributeError):
                                    raise ImportError("Could not import GenerativeModel. Please ensure google-cloud-aiplatform>=1.40.0 is installed.")
                
                self.model = GenerativeModel("gemini-2.5-pro")
                # Create Google Search grounding tool for Gemini 2.0
                # Use google_search field instead of google_search_retrieval
                if Tool is not None:
                    self.search_tool = Tool.from_dict({"google_search": {}})
                else:
                    # Fallback: create tool dict directly
                    self.search_tool = {"google_search": {}}
                self._log("Scout: Vertex AI Grounding with Google Search initialized.", "engineering")
            except Exception as e:
                print(f"⚠️  Failed to load Gemini model: {e}")
                self.model = None
                self.search_tool = None
                self._log(f"Scout: Failed to initialize Google Search Grounding: {e}. Using AI analysis only.", "engineering")
    
    def _log(self, message: str, log_type: str = "engineering"):
        """Internal logging method."""
        if self.log_callback:
            self.log_callback(message, log_type, self.conversation_turn, self.user_input)
        else:
            print(f"🟢 {message}")
    
    def _get_response_text(self, response) -> str:
        """
        Safely extract text from Vertex AI response, handling both single-part and multi-part responses.
        
        Args:
            response: The response object from GenerativeModel.generate_content()
            
        Returns:
            Extracted text as string, or empty string if unavailable
        """
        try:
            # Try the simple case first (single-part response)
            return response.text
        except ValueError:
            # Handle multi-part responses
            try:
                if hasattr(response, 'candidates') and response.candidates:
                    text_parts = []
                    for candidate in response.candidates:
                        if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                            for part in candidate.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    text_parts.append(part.text)
                    return "".join(text_parts)
            except Exception:
                pass
            return ""
    
    def _call_gemini(self, prompt: str) -> str:
        """
        Call Gemini model with a prompt.
        
        Args:
            prompt: The prompt to send to Gemini
            
        Returns:
            Response text from Gemini, or empty string if unavailable
        """
        if not self.model:
            return ""
        
        try:
            response = self.model.generate_content(prompt)
            return self._get_response_text(response)
        except Exception as e:
            self._log(f"Gemini API error: {str(e)}", "engineering")
            return ""
    
    def _format_chat_history(self, chat_history: list) -> str:
        """Format chat history for inclusion in prompts."""
        if not chat_history:
            return "No previous conversation."
        
        formatted = []
        for msg in chat_history[-5:]:  # Last 5 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                formatted.append(f'User: "{content}"')
            elif role == "assistant":
                # Truncate long assistant responses, but keep code blocks visible
                if "```terraform" in content.lower():
                    # Extract just the code block for context
                    code_start = content.lower().find("```terraform")
                    code_end = content.find("```", code_start + 12)
                    if code_end != -1:
                        code_snippet = content[code_start:code_end+3]
                        formatted.append(f'AI: "Here is the code...\n{code_snippet}"')
                    else:
                        content_preview = content[:200] + "..." if len(content) > 200 else content
                        formatted.append(f'AI: "{content_preview}"')
                else:
                    content_preview = content[:200] + "..." if len(content) > 200 else content
                    formatted.append(f'AI: "{content_preview}"')
        
        # Format as conversation flow
        if formatted:
            return " -> ".join(formatted)
        return "No previous conversation."
    
    def _extract_previous_code(self, chat_history: list) -> str:
        """Extract previous Terraform code from chat history."""
        if not chat_history:
            return ""
        
        # Look for Terraform code blocks in assistant responses
        for msg in reversed(chat_history[-10:]):  # Check last 10 messages
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                # Look for ```terraform blocks
                if "```terraform" in content.lower():
                    # Extract code between ```terraform and ```
                    start = content.lower().find("```terraform")
                    if start != -1:
                        start = content.find("\n", start) + 1
                        end = content.find("```", start)
                        if end != -1:
                            code = content[start:end].strip()
                            if code:
                                return code
        return ""
    
    def _scout_agent(self, user_request: str, chat_history: list = None, execution_logs: list = None) -> Dict[str, str]:
        """
        Scout Agent: Researches request using Vertex AI Grounding with Google Search.
        Uses Google Search grounding tool to automatically search the web and analyze results.
        
        Args:
            user_request: The user's engineering request
            chat_history: Previous conversation messages for context
            execution_logs: Optional list to append execution logs to
            
        Returns:
            Dictionary of requirements
        """
        log_msg = "🟢 Scout: Analyzing request and researching with Google Search grounding..."
        self._log("Scout: Analyzing request and researching with Google Search grounding...", "engineering")
        if execution_logs is not None:
            execution_logs.append(log_msg)
        
        # Format history for prompt
        history_text = self._format_chat_history(chat_history) if chat_history else "No previous conversation."
        
        # Load training examples for Engineering (learned from QA tests and feedback)
        training_examples = feedback.get_training_examples(department="Engineering", active_only=True)
        training_examples_text = "None"
        if training_examples:
            lines = []
            for ex in training_examples[:10]:  # Limit to 10 most recent
                lines.append(f"- Query: \"{ex['example_query']}\" → Expected: {ex['expected_behavior']}")
            training_examples_text = "\n".join(lines)
        
        # Use Vertex AI with Google Search grounding
        if VERTEX_AI_AVAILABLE and self.search_tool:
            try:
                # Create a model instance with the search tool for grounding
                scout_model = GenerativeModel("gemini-2.5-flash", tools=[self.search_tool])
                
                prompt = f"""You are an Expert Google Cloud Architect and DevOps Engineer. Analyze: "{user_request}"

**YOUR ROLE:**
- You are an Expert Google Cloud Architect and DevOps Engineer with deep knowledge of GCP services, best practices, and architectural patterns.
- When asked coding questions (Terraform, Python, gcloud), provide valid, production-ready code.
- When asked architectural questions (e.g., "Spanner vs. SQL", "Why use X?", "What's the difference?", "Should I use..."), explain the TRADE-OFFS, best practices, and decision criteria in a narrative style.
- Always prioritize Google Cloud security best practices (e.g., Least Privilege, Private IPs, Shielded VMs).

**CRITICAL FIRST STEP:** Determine if the user wants:
- **Architectural Explanation** (Questions like "Why?", "What's the difference?", "Should I use X or Y?", "Explain...", "Compare...", "When to use...", "How do I...", "How to...", "What is the best way...", "What is the most secure way...")
- **Terraform code** (Infrastructure-as-Code for GCP resources like VMs, buckets, networks)
- **Python script** (Code to interact with GCP APIs, list resources, automate tasks)
- **Other code** (Shell scripts, explanations, etc.)

**If the user asks architectural questions (e.g., "Why use Cloud SQL?", "Spanner vs. BigQuery", "What's the difference between...", "Should I use...", "When to use...", "Explain...", "Compare...", "How do I ensure...", "How to configure...", "What is the best way...", "What is the most secure way...") → This is an ARCHITECTURAL_EXPLANATION request, NOT code generation.**

**If the user asks for a "Python script", "Python code", "script to list", "script to manage", or similar → This is a PYTHON SCRIPT request, NOT Terraform.**

**Context:** You are part of an ongoing conversation. Use the **History** below to resolve references like 'it', 'that', 'the previous code', 'the VM', 'the bucket', or any pronouns.

**History:**
{history_text}

**Training Examples (use these to guide output type and behavior for similar queries):**
{training_examples_text}

**Current Request:** {user_request}

**Task:**
1. **First, determine the output type:**
   - If user asks architectural questions ("Why?", "What's the difference?", "Should I use...", "When to use...", "Explain...", "Compare...", "vs.", "versus", "How do I...", "How to...", "What is the best way...", "What is the most secure way...") → Output Type: **ARCHITECTURAL_EXPLANATION**
   - If user asks for "Python script", "Python code", "script to", "write a script", "list all", "manage", "automate" → Output Type: **PYTHON_SCRIPT**
   - If user asks for "Terraform", "Infrastructure", "deploy", "create VM", "create bucket", "IaC" → Output Type: **TERRAFORM**
   - Otherwise → Output Type: **TERRAFORM** (default for infrastructure requests)

2. **If Output Type is ARCHITECTURAL_EXPLANATION:**
   - Question Type: [comparison|explanation|recommendation|best_practice]
   - Topics: [List the GCP services/concepts being discussed]
   - Context: [What is the user trying to achieve?]
   - Key Decision Factors: [What criteria should guide the decision? - e.g., scale, cost, consistency, latency]

3. **If Output Type is PYTHON_SCRIPT:**
   - Code Type: [python_script]
   - Purpose: [What the script should do - e.g., "List all VM instances", "Manage storage buckets"]
   - GCP Service: [Which GCP service/API to use - e.g., "Compute Engine API", "Storage API"]
   - Authentication: [How to authenticate - e.g., "Application Default Credentials", "Service Account Key"]
   - Output Format: [What the script should output - e.g., "Print VM names and zones", "Return JSON"]

3. **If Output Type is TERRAFORM:**
   - Resource Type: [compute_instance|storage_bucket|compute_network|gke_autopilot|project|other]
   - **If the user asks for GKE, Kubernetes, Autopilot cluster, or container cluster, use Resource Type: gke_autopilot.**
   - Region: [us-east1|us-central1|europe-west1|asia-east1|other] - **MUST be us-east1 unless user explicitly requests another**
   - Security Level: [strict|standard|relaxed]
   - Additional Requirements: [ONLY requirements relevant to the specific resource type requested]
   - Resources NOT Needed: [explicitly list what the user did NOT ask for]
   - **Bill of Materials:** Explicitly list the resources required. Add a note: 'NO other resources required.'
   - **Dependency Expansion (CRITICAL):**
     * **Networking:** If the user asks for a specific network feature (like Cloud NAT, Private IP, or Firewall Rules), you MUST explicitly list the underlying infrastructure required.
     * **Identity:** If a VM is requested → You MUST list `google_service_account`.
     * **Storage:** If a Bucket is requested → You MUST list `google_kms_key_ring` and `google_kms_crypto_key` ONLY IF encryption is explicitly asked for.

Based on your research using Google Search, provide a structured response matching the Output Type determined above.

Be concise and specific."""
                
                log_msg = "🟢 Scout: Searching web and analyzing with Vertex AI Grounding..."
                self._log("Scout: Searching web and analyzing with Vertex AI Grounding...", "engineering")
                if execution_logs is not None:
                    execution_logs.append(log_msg)
                
                response = scout_model.generate_content(prompt)
                
                if response:
                    response_text = self._get_response_text(response)
                    
                    if response_text:
                        self._log(f"Scout: Grounded research complete. {response_text[:100]}...", "engineering")
                        # Check if grounding metadata is available
                        if hasattr(response, 'grounding_metadata') and response.grounding_metadata:
                            log_msg = "🟢 Scout: Google Search grounding was used in this response."
                            self._log("Scout: Google Search grounding was used in this response.", "engineering")
                            if execution_logs is not None:
                                execution_logs.append(log_msg)
                        # Parse response to extract requirements
                        log_msg = "🟢 Scout: Parsing requirements from research results..."
                        if execution_logs is not None:
                            execution_logs.append(log_msg)
                        requirements = self._parse_scout_response(response_text, user_request)
                    else:
                        log_msg = "🟢 Scout: No response text from grounded model. Using fallback analysis."
                        self._log("Scout: No response text from grounded model. Using fallback analysis.", "engineering")
                        if execution_logs is not None:
                            execution_logs.append(log_msg)
                        requirements = self._extract_requirements_fallback(user_request)
                else:
                    log_msg = "🟢 Scout: No response from grounded model. Using fallback analysis."
                    self._log("Scout: No response from grounded model. Using fallback analysis.", "engineering")
                    if execution_logs is not None:
                        execution_logs.append(log_msg)
                    requirements = self._extract_requirements_fallback(user_request)
            except Exception as e:
                log_msg = f"🟢 Scout: Grounding error: {e}. Falling back to AI analysis only."
                self._log(f"Scout: Grounding error: {e}. Falling back to AI analysis only.", "engineering")
                if execution_logs is not None:
                    execution_logs.append(log_msg)
                # Fallback to model without grounding
                if self.model:
                    prompt = f"""You are an Expert Google Cloud Architect and DevOps Engineer. Analyze: "{user_request}"

**YOUR ROLE:**
- You are an Expert Google Cloud Architect and DevOps Engineer with deep knowledge of GCP services, best practices, and architectural patterns.
- When asked coding questions (Terraform, Python, gcloud), provide valid, production-ready code.
- When asked architectural questions (e.g., "Spanner vs. SQL", "Why use X?", "What's the difference?", "Should I use..."), explain the TRADE-OFFS, best practices, and decision criteria in a narrative style.
- Always prioritize Google Cloud security best practices (e.g., Least Privilege, Private IPs, Shielded VMs).

**CRITICAL FIRST STEP:** Determine if this is an architectural question (e.g., "Why?", "What's the difference?", "Should I use...", "Compare...") or a code generation request.

**Context:** You are part of an ongoing conversation. Use the **History** below to resolve references like 'it', 'that', 'the previous code', 'the VM', 'the bucket', or any pronouns.

**History:**
{history_text}

**Current Request:** {user_request}

**Default Constraint:** Unless the user EXPLICITLY requests a specific region (e.g., "us-central1", "europe-west1"), ALL requirements MUST specify `us-east1`. Do NOT use `us-central1` or any other region as default.

**Task:**
1. Interpret the current request *in the context of the history*. If the user refers to 'it', 'the VM', 'the bucket', 'that resource', or uses pronouns, look at the history to identify what resource they're referring to.
2. List ONLY the specific GCP resources requested (considering context from history).
3. **Dependency Expansion (CRITICAL):**
   * **Networking:** If the user asks for a specific network feature (like Cloud NAT, Private IP, or Firewall Rules), you MUST explicitly list the underlying infrastructure required.
     * *Rule:* If 'Cloud NAT' is requested → You MUST list: `google_compute_network` (VPC), `google_compute_subnetwork`, `google_compute_router`, AND `google_compute_router_nat`.
     * *Rule:* Never suggest using the 'default' network. Always define a custom VPC/Subnet.
   * **Identity:** If a VM is requested → You MUST list `google_service_account`.
   * **Storage:** If a Bucket is requested → You MUST list `google_kms_key_ring` and `google_kms_crypto_key` ONLY IF encryption is explicitly asked for. Otherwise, standard encryption is fine.
4. Explicitly state what is NOT needed (e.g., 'No VMs requested', 'No networks requested').
5. **Context Filter:** Only list requirements that are *technically valid* for the specific resources.
   - Do NOT suggest network rules for non-network resources like Storage/BigQuery.
   - Do NOT suggest compute-specific security (like shielded VMs) for storage buckets.
   - Do NOT suggest firewall rules for resources that don't use firewalls.

Provide a structured response:
- Resource Type: [compute_instance|storage_bucket|compute_network|gke_autopilot|project|other]
- **If the user asks for GKE, Kubernetes, Autopilot cluster, or container cluster, use Resource Type: gke_autopilot.**
- Region: [us-east1|us-central1|europe-west1|asia-east1|other] - **MUST be us-east1 unless user explicitly requests another**
- Security Level: [strict|standard|relaxed]
- **Specific Configuration Requirements (CRITICAL):** List ALL specific features, settings, and configurations the user explicitly requested. For example:
  * If user asks for "versioning enabled" → Include: "versioning: enabled"
  * If user asks for "lifecycle rule to delete after 30 days" → Include: "lifecycle_rule: delete after 30 days"
  * If user asks for "machine type e2-medium" → Include: "machine_type: e2-medium"
  * If user asks for "zone us-central1-a" → Include: "zone: us-central1-a"
  * Capture EVERY specific detail mentioned in the user's request
- Additional Requirements: [ONLY requirements relevant to the specific resource type requested]
- Resources NOT Needed: [explicitly list what the user did NOT ask for]

Be concise and specific."""
                    response = self._call_gemini(prompt)
                    if response:
                        requirements = self._parse_scout_response(response, user_request)
                    else:
                        requirements = self._extract_requirements_fallback(user_request)
                else:
                    requirements = self._extract_requirements_fallback(user_request)
        elif VERTEX_AI_AVAILABLE and self.model:
            # Fallback: Use model without grounding
            self._log("Scout: Google Search grounding not available. Using AI analysis only.", "engineering")
            prompt = f"""You are an Expert Google Cloud Architect and DevOps Engineer. Analyze: "{user_request}"

**YOUR ROLE:**
- You are an Expert Google Cloud Architect and DevOps Engineer with deep knowledge of GCP services, best practices, and architectural patterns.
- When asked coding questions (Terraform, Python, gcloud), provide valid, production-ready code.
- When asked architectural questions (e.g., "Spanner vs. SQL", "Why use X?", "What's the difference?", "Should I use..."), explain the TRADE-OFFS, best practices, and decision criteria in a narrative style.
- Always prioritize Google Cloud security best practices (e.g., Least Privilege, Private IPs, Shielded VMs).

**CRITICAL FIRST STEP:** Determine if this is an architectural question (e.g., "Why?", "What's the difference?", "Should I use...", "Compare...") or a code generation request.

**Context:** You are part of an ongoing conversation. Use the **History** below to resolve references like 'it', 'that', 'the previous code', 'the VM', 'the bucket', or any pronouns.

**History:**
{history_text}

**Current Request:** {user_request}

**Default Constraint:** Unless the user EXPLICITLY requests a specific region (e.g., "us-central1", "europe-west1"), ALL requirements MUST specify `us-east1`. Do NOT use `us-central1` or any other region as default.

**Task:**
1. Interpret the current request *in the context of the history*. If the user refers to 'it', 'the VM', 'the bucket', 'that resource', or uses pronouns, look at the history to identify what resource they're referring to.
2. List ONLY the specific GCP resources requested (considering context from history).
3. **Dependency Expansion (CRITICAL):**
   * **Networking:** If the user asks for a specific network feature (like Cloud NAT, Private IP, or Firewall Rules), you MUST explicitly list the underlying infrastructure required.
     * *Rule:* If 'Cloud NAT' is requested → You MUST list: `google_compute_network` (VPC), `google_compute_subnetwork`, `google_compute_router`, AND `google_compute_router_nat`.
     * *Rule:* Never suggest using the 'default' network. Always define a custom VPC/Subnet.
   * **Identity:** If a VM is requested → You MUST list `google_service_account`.
   * **Storage:** If a Bucket is requested → You MUST list `google_kms_key_ring` and `google_kms_crypto_key` ONLY IF encryption is explicitly asked for. Otherwise, standard encryption is fine.
4. Explicitly state what is NOT needed (e.g., 'No VMs requested', 'No networks requested').
5. **Context Filter:** Only list requirements that are *technically valid* for the specific resources.
   - Do NOT suggest network rules for non-network resources like Storage/BigQuery.
   - Do NOT suggest compute-specific security (like shielded VMs) for storage buckets.
   - Do NOT suggest firewall rules for resources that don't use firewalls.

Provide a structured response:
- Resource Type: [compute_instance|storage_bucket|compute_network|gke_autopilot|project|other]
- **If the user asks for GKE, Kubernetes, Autopilot cluster, or container cluster, use Resource Type: gke_autopilot.**
- Region: [us-east1|us-central1|europe-west1|asia-east1|other] - **MUST be us-east1 unless user explicitly requests another**
- Security Level: [strict|standard|relaxed]
- **Specific Configuration Requirements (CRITICAL):** List ALL specific features, settings, and configurations the user explicitly requested. For example:
  * If user asks for "versioning enabled" → Include: "versioning: enabled"
  * If user asks for "lifecycle rule to delete after 30 days" → Include: "lifecycle_rule: delete after 30 days"
  * If user asks for "machine type e2-medium" → Include: "machine_type: e2-medium"
  * If user asks for "zone us-central1-a" → Include: "zone: us-central1-a"
  * Capture EVERY specific detail mentioned in the user's request
- Additional Requirements: [ONLY requirements relevant to the specific resource type requested]
- Resources NOT Needed: [explicitly list what the user did NOT ask for]

Be concise and specific."""
            response = self._call_gemini(prompt)
            if response:
                requirements = self._parse_scout_response(response, user_request)
            else:
                requirements = self._extract_requirements_fallback(user_request)
        else:
            # Mock mode: use keyword-based extraction
            time.sleep(0.25)
            requirements = self._extract_requirements_fallback(user_request)
        
        log_msg = "🟢 Scout: Requirements gathered. Passing to Coder."
        self._log("Scout: Requirements gathered. Passing to Coder.", "engineering")
        if execution_logs is not None:
            execution_logs.append(log_msg)
        return requirements
    
    def _parse_scout_response(self, response: str, user_request: str) -> Dict[str, str]:
        """Parse Scout's AI response into requirements dictionary."""
        response_lower = response.lower()
        user_lower = user_request.lower()
        
        # First, check if this is an architectural question
        architectural_keywords = [
            "why", "what's the difference", "what is the difference", "should i use", "when to use",
            "explain", "compare", "versus", " vs ", "recommend", "best practice", "trade-off",
            "tradeoff", "pros and cons", "advantages", "disadvantages", "which is better",
            "architectural", "architecture", "design decision", "how do i", "how to", "how can i",
            "what is the best way", "what is the most secure way", "what is the recommended"
        ]
        is_architectural = any(keyword in user_lower for keyword in architectural_keywords) or \
                          ("architectural_explanation" in response_lower)
        
        if is_architectural:
            # This is an architectural explanation request
            requirements = {
                "output_type": "architectural_explanation",
                "question_type": "comparison" if ("vs" in user_lower or "versus" in user_lower or "compare" in user_lower) else \
                                "recommendation" if ("should" in user_lower or "recommend" in user_lower) else \
                                "best_practice" if ("how do i" in user_lower or "how to" in user_lower or "how can i" in user_lower or "what is the best way" in user_lower or "what is the most secure way" in user_lower) else \
                                "explanation",
                "topics": user_request  # Will be extracted by the explanation generator
            }
            return requirements
        
        # Second, check if this is a Python script request
        if ("python" in response_lower and "script" in response_lower) or \
           ("python_script" in response_lower) or \
           ("python script" in user_lower) or \
           ("script to" in user_lower and "terraform" not in user_lower) or \
           ("write a script" in user_lower) or \
           ("list all" in user_lower and "terraform" not in user_lower):
            # This is a Python script request
            # Determine the GCP service based on the user's request
            gcp_service = "gcp_api"
            purpose = "custom_script"
            
            if "storage" in user_lower or "bucket" in user_lower or "blob" in user_lower or "file" in user_lower:
                gcp_service = "storage_api"
                purpose = "list_storage_blobs" if ("list" in user_lower or "blob" in user_lower or "file" in user_lower) else "storage_operations"
            elif "pubsub" in user_lower or "pub/sub" in user_lower or "publish" in user_lower or "topic" in user_lower:
                gcp_service = "pubsub_api"
                purpose = "publish_message" if "publish" in user_lower else "pubsub_operations"
            elif "vm" in user_lower or "instance" in user_lower or "compute" in user_lower:
                gcp_service = "compute_engine_api"
                purpose = "list_all_vm_instances" if ("list" in user_lower or "all" in user_lower) else "compute_operations"
            elif "bigquery" in user_lower or "bq" in user_lower:
                gcp_service = "bigquery_api"
                purpose = "bigquery_operations"
            
            requirements = {
                "output_type": "python_script",
                "purpose": purpose,
                "gcp_service": gcp_service,
                "authentication": "application_default_credentials",
                "full_user_request": user_request  # Store full request for Coder
            }
            return requirements
        
        # Default to Terraform
        requirements = {
            "output_type": "terraform",
            "resource": "compute_instance",
            "region": "us-east1",
            "security": "strict",
            "specific_config": ""  # Store specific configuration requirements
        }
        
        # Extract resource type (GKE/Autopilot first so it is not overwritten by "compute"/"instance")
        if any(k in response_lower or k in user_lower for k in ("gke", "autopilot", "kubernetes", "container cluster", "container_cluster")):
            requirements["resource"] = "gke_autopilot"
        elif "storage" in response_lower or "bucket" in response_lower:
            requirements["resource"] = "storage_bucket"
        elif "network" in response_lower or "vpc" in response_lower:
            requirements["resource"] = "compute_network"
        elif "compute" in response_lower or "instance" in response_lower or "vm" in response_lower:
            requirements["resource"] = "compute_instance"
        
        # Extract region - only override if explicitly mentioned
        if "europe" in response_lower or "eu" in response_lower or "europe" in user_lower:
            requirements["region"] = "europe-west1"
        elif "asia" in response_lower or "asia" in user_lower:
            requirements["region"] = "asia-east1"
        elif "us-central" in response_lower or "us-central" in user_lower:
            requirements["region"] = "us-central1"
        elif "us-east" in response_lower or "us-east" in user_lower:
            requirements["region"] = "us-east1"
        # If no region explicitly mentioned, default to us-east1 (already set above)
        
        # Extract security level
        if "strict" in response_lower:
            requirements["security"] = "strict"
        elif "relaxed" in response_lower or "insecure" in user_request.lower():
            requirements["security"] = "relaxed"
        
        # Extract specific configuration requirements from the response
        # Look for patterns like "versioning", "lifecycle", "machine_type", etc.
        specific_configs = []
        
        # Storage bucket specific
        if "versioning" in response_lower or "versioning" in user_lower:
            specific_configs.append("versioning: enabled")
        if "lifecycle" in response_lower or "lifecycle" in user_lower:
            # Try to extract lifecycle details
            if "30 days" in user_lower or "30 day" in user_lower:
                specific_configs.append("lifecycle_rule: delete after 30 days")
            elif "delete" in user_lower and ("day" in user_lower or "days" in user_lower):
                specific_configs.append("lifecycle_rule: delete based on age")
        
        # Compute instance specific
        if "e2-medium" in user_lower or "e2-medium" in response_lower:
            specific_configs.append("machine_type: e2-medium")
        if "us-central1-a" in user_lower or "us-central1-a" in response_lower:
            specific_configs.append("zone: us-central1-a")
        if "web-server" in user_lower or "web-server" in response_lower:
            specific_configs.append("name: web-server")
        
        # Network specific
        if "subnet" in response_lower or "subnet" in user_lower:
            specific_configs.append("subnet: required")
        
        # Store all specific configs
        if specific_configs:
            requirements["specific_config"] = "; ".join(specific_configs)
        
        # Also store the full user request for the Coder to parse
        requirements["full_user_request"] = user_request
        
        return requirements
    
    def _extract_requirements_fallback(self, user_request: str) -> Dict[str, str]:
        """Fallback keyword-based requirements extraction."""
        user_lower = user_request.lower()
        
        # First, check if this is an architectural question
        architectural_keywords = [
            "why", "what's the difference", "what is the difference", "should i use", "when to use",
            "explain", "compare", "versus", " vs ", "recommend", "best practice", "trade-off",
            "tradeoff", "pros and cons", "advantages", "disadvantages", "which is better"
        ]
        is_architectural = any(keyword in user_lower for keyword in architectural_keywords)
        
        if is_architectural:
            # This is an architectural explanation request
            requirements = {
                "output_type": "architectural_explanation",
                "question_type": "comparison" if ("vs" in user_lower or "versus" in user_lower or "compare" in user_lower) else \
                                "recommendation" if ("should" in user_lower or "recommend" in user_lower) else \
                                "explanation",
                "topics": user_request
            }
            return requirements
        
        # Second, check if this is a Python script request
        if ("python" in user_lower and "script" in user_lower) or \
           ("script to" in user_lower and "terraform" not in user_lower) or \
           ("write a script" in user_lower) or \
           ("list all" in user_lower and "terraform" not in user_lower):
            # This is a Python script request
            # Determine the GCP service based on the user's request
            gcp_service = "gcp_api"
            purpose = "custom_script"
            
            if "storage" in user_lower or "bucket" in user_lower or "blob" in user_lower or "file" in user_lower:
                gcp_service = "storage_api"
                purpose = "list_storage_blobs" if ("list" in user_lower or "blob" in user_lower or "file" in user_lower) else "storage_operations"
            elif "pubsub" in user_lower or "pub/sub" in user_lower or "publish" in user_lower or "topic" in user_lower:
                gcp_service = "pubsub_api"
                purpose = "publish_message" if "publish" in user_lower else "pubsub_operations"
            elif "vm" in user_lower or "instance" in user_lower or "compute" in user_lower:
                gcp_service = "compute_engine_api"
                purpose = "list_all_vm_instances" if ("list" in user_lower or "all" in user_lower) else "compute_operations"
            elif "bigquery" in user_lower or "bq" in user_lower:
                gcp_service = "bigquery_api"
                purpose = "bigquery_operations"
            
            requirements = {
                "output_type": "python_script",
                "purpose": purpose,
                "gcp_service": gcp_service,
                "authentication": "application_default_credentials",
                "full_user_request": user_request  # Store full request for Coder
            }
            return requirements
        
        # Default to Terraform
        requirements = {
            "output_type": "terraform",
            "resource": "compute_instance",
            "region": "us-east1",  # Default to us-east1
            "security": "strict",
            "specific_config": "",  # Store specific configuration requirements
            "full_user_request": user_request  # Store full request for Coder
        }
        
        if any(k in user_lower for k in ("gke", "autopilot", "kubernetes", "container cluster", "container_cluster")):
            requirements["resource"] = "gke_autopilot"
        elif "storage" in user_lower or "bucket" in user_lower:
            requirements["resource"] = "storage_bucket"
        elif "network" in user_lower or "vpc" in user_lower:
            requirements["resource"] = "compute_network"
        
        # Only override region if explicitly mentioned
        if "europe" in user_lower or "eu" in user_lower:
            requirements["region"] = "europe-west1"
        elif "asia" in user_lower:
            requirements["region"] = "asia-east1"
        elif "us-central" in user_lower:
            requirements["region"] = "us-central1"
        elif "us-east" in user_lower:
            requirements["region"] = "us-east1"
        # Otherwise, keep default us-east1
        
        # Extract specific configuration requirements
        specific_configs = []
        
        # Storage bucket specific
        if "versioning" in user_lower:
            specific_configs.append("versioning: enabled")
        if "lifecycle" in user_lower:
            if "30 days" in user_lower or "30 day" in user_lower:
                specific_configs.append("lifecycle_rule: delete after 30 days")
            elif "delete" in user_lower and ("day" in user_lower or "days" in user_lower):
                specific_configs.append("lifecycle_rule: delete based on age")
        
        # Compute instance specific
        if "e2-medium" in user_lower:
            specific_configs.append("machine_type: e2-medium")
        if "us-central1-a" in user_lower:
            specific_configs.append("zone: us-central1-a")
        if "web-server" in user_lower:
            specific_configs.append("name: web-server")
        
        # Network specific
        if "subnet" in user_lower:
            specific_configs.append("subnet: required")
        
        if specific_configs:
            requirements["specific_config"] = "; ".join(specific_configs)
        
        return requirements
    
    def _coder_agent(self, requirements: Dict[str, str], scout_output: str = "", sentinel_feedback: str = "", previous_code: str = "", chat_history: list = None, execution_logs: list = None) -> str:
        """
        Coder Agent: Generates Terraform configuration or Python scripts using Vertex AI.
        
        Args:
            requirements: Dictionary of requirements from Scout
            scout_output: Original scout analysis output
            sentinel_feedback: Optional feedback from Sentinel about security issues to fix
            previous_code: Previous code from history (for iterative edits)
            chat_history: Previous conversation messages for context
            
        Returns:
            Code as string (Terraform HCL or Python)
        """
        output_type = requirements.get("output_type", "terraform")
        
        # Handle Architectural Explanation generation
        if output_type == "architectural_explanation":
            log_msg = "🟢 Coder: Drafting architectural explanation..."
            self._log("Coder: Drafting architectural explanation...", "engineering")
            if execution_logs is not None:
                execution_logs.append(log_msg)
            
            question_type = requirements.get("question_type", "explanation")
            topics = requirements.get("topics", [])
            
            # Format history for prompt
            history_text = self._format_chat_history(chat_history) if chat_history else "No previous conversation."
            
            if VERTEX_AI_AVAILABLE and self.model:
                architectural_prompt = f"""You are an Expert Google Cloud Architect and DevOps Engineer.

**User Request:** {scout_output if scout_output else "Explain Google Cloud architecture"}

**Context:** If the user is asking a follow-up question, use the **History** to understand the context.

**History:**
{history_text}

**Question Type:** {question_type}
**Topics:** {', '.join(topics) if isinstance(topics, list) else topics}

**Your Task:**
Determine if the user is asking for INFRASTRUCTURE CODE (Terraform/Python) or a CONCEPTUAL EXPLANATION.

**Since this is a CONCEPTUAL EXPLANATION request, you must:**

1. **Output Format:** Write a clear, professional technical explanation in standard Markdown format.
   - Use headers (##, ###), bullet points, and paragraphs
   - DO NOT wrap the text in code blocks (```) or Terraform comments
   - DO NOT include Terraform code unless the user explicitly asks for it
   - Write in narrative style, explaining concepts, trade-offs, and best practices

2. **Content Requirements:**
   - **For Comparisons (vs, versus, compare):** Explain the differences, trade-offs, use cases, and when to choose each option
   - **For Recommendations (should i use, recommend):** Provide decision criteria, justification, and alternatives
   - **For Explanations (explain, what is, why use):** Clarify the concept, when/why to use it, key features, and security considerations
   - Always prioritize Google Cloud security best practices (e.g., Least Privilege, Private IPs)
   - Include real-world examples and best practices

3. **Structure:**
   - Introduction: Brief overview
   - Key Points: Main concepts or differences
   - Trade-offs: Pros and cons, performance, cost, complexity
   - Recommendation: When to use each option (if applicable)
   - Security Considerations: Best practices

**Output:** Return ONLY the Markdown explanation text. No code blocks, no Terraform syntax, no ``` fences. Just clean, professional technical prose.

Generate a comprehensive, well-structured architectural explanation."""
                
                explanation = self._call_gemini(architectural_prompt)
                
                if explanation:
                    self._log("Coder: Architectural explanation generated.", "engineering")
                    return explanation
                else:
                    # Fallback explanation
                    return f"## {topics[0] if topics else 'Architecture Explanation'}\n\nThis is a conceptual question about Google Cloud architecture. Please provide more specific details about what you'd like to understand."
            else:
                # Mock mode: return basic explanation
                time.sleep(0.25)
                return f"## {topics[0] if topics else 'Architecture Explanation'}\n\nThis is a conceptual question about Google Cloud architecture. Please provide more specific details about what you'd like to understand."
        
        # Handle Python script generation
        if output_type == "python_script":
            if sentinel_feedback:
                log_msg = "🟢 Coder: Rewriting Python script based on feedback..."
                self._log("Coder: Rewriting Python script based on feedback...", "engineering")
            else:
                log_msg = "🟢 Coder: Drafting Python script..."
                self._log("Coder: Drafting Python script...", "engineering")
            if execution_logs is not None:
                execution_logs.append(log_msg)
            
            purpose = requirements.get("purpose", "custom_script")
            gcp_service = requirements.get("gcp_service", "gcp_api")
            
            # Format history for prompt
            history_text = self._format_chat_history(chat_history) if chat_history else "No previous conversation."
            
            if VERTEX_AI_AVAILABLE and self.model:
                # Get full user request for better context
                full_user_request = requirements.get("full_user_request", scout_output if scout_output else "")
                
                # Build service-specific instructions
                service_instructions = ""
                if gcp_service == "storage_api" or "storage" in purpose.lower():
                    service_instructions = """
**If the user asks to "list files/blobs in a Storage bucket", create a script that:
1. Uses the Storage API (`from google.cloud import storage`)
2. Creates a Storage client: `storage.Client()`
3. Gets a bucket: `client.bucket(bucket_name)`
4. Lists blobs: `bucket.list_blobs()` or `bucket.list_blobs(prefix=...)`
5. Prints blob names, sizes, and other metadata
6. Handles authentication using ADC
7. Includes error handling

**Code Requirements:**
- Use `from google.cloud import storage`
- Use `storage.Client()` for the client
- Use `bucket.list_blobs()` to iterate through blobs
- Print blob information in a readable format"""
                elif gcp_service == "pubsub_api" or "pubsub" in purpose.lower() or "publish" in purpose.lower():
                    service_instructions = """
**If the user asks to "publish a message to Pub/Sub", create a script that:
1. Uses the Pub/Sub API (`from google.cloud import pubsub_v1`)
2. Creates a Publisher client: `pubsub_v1.PublisherClient()`
3. Constructs topic path: `publisher.topic_path(project_id, topic_name)`
4. Publishes message: `publisher.publish(topic_path, data, **attributes)`
5. Handles the future result
6. Handles authentication using ADC
7. Includes error handling

**Code Requirements:**
- Use `from google.cloud import pubsub_v1`
- Use `pubsub_v1.PublisherClient()` for the client
- Use `publisher.publish()` to publish messages
- Handle the returned future object
- Print success/error messages"""
                elif gcp_service == "compute_engine_api" or "vm" in purpose.lower() or "instance" in purpose.lower():
                    service_instructions = """
**If the user asks to "list all VM instances", create a script that:
1. Uses the Compute Engine API (`from google.cloud import compute_v1`)
2. Creates InstancesClient: `compute_v1.InstancesClient()`
3. Lists all zones, then lists instances in each zone
4. Prints instance name, zone, machine type, and status
5. Handles authentication using ADC
6. Includes error handling

**Code Requirements:**
- Use `from google.cloud import compute_v1`
- Use `compute_v1.InstancesClient()` and `compute_v1.ZonesClient()`
- Iterate through zones and list instances
- Print instance information in a readable format"""
                else:
                    service_instructions = """
**Code Requirements:**
- Use the appropriate Google Cloud Python client library based on the user's request
- Include proper imports (e.g., `from google.cloud import <service>`)
- Use Application Default Credentials for authentication
- Include error handling (try/except blocks)
- Print results in a readable format
- Include comments for clarity"""
                
                python_prompt = f"""You are a Python Developer. Write a Python script to interact with Google Cloud Platform APIs.

**User Request:** {full_user_request if full_user_request else scout_output if scout_output else "Generate a Python script"}

**Context:** If the user is asking for a modification, use the **History** to locate the previous code and apply the changes.

**History:**
{history_text}

**Requirements:**
- Purpose: {purpose}
- GCP Service: {gcp_service}
- Authentication: Use Application Default Credentials (ADC) - `google.auth.default()` or `google.auth.default(scopes=[...])`
- Output: Print results in a readable format (JSON or formatted text)

{service_instructions}

**IMPORTANT: Code Formatting (CRITICAL):**
- When writing code (Terraform or Python), you MUST use proper indentation and NEWLINES.
- Do NOT minify the code. Output readable, multi-line code.
- Use proper Python indentation (4 spaces per level).
- Add blank lines between functions and logical sections.
- Include comments for clarity.

**Output:** Return ONLY the Python code. No markdown text, no explanations, no code fences. Start with `#!/usr/bin/env python3` if appropriate.

Generate complete, production-ready Python code that matches the user's request exactly."""
                
                python_code = self._call_gemini(python_prompt)
                
                if python_code:
                    self._log("Coder: AI-generated Python script complete.", "engineering")
                    return python_code
                else:
                    # Fallback template
                    return self._generate_python_template(purpose, gcp_service)
            else:
                # Mock mode: use template
                time.sleep(0.25)
                return self._generate_python_template(purpose, gcp_service)
        
        # Terraform generation (existing logic)
        if sentinel_feedback:
            log_msg = "🟢 Coder: Rewriting code based on Sentinel feedback..."
            self._log("Coder: Rewriting code based on Sentinel feedback...", "engineering")
        else:
            log_msg = "🟢 Coder: Drafting Terraform configuration..."
            self._log("Coder: Drafting Terraform configuration...", "engineering")
        if execution_logs is not None:
            execution_logs.append(log_msg)
        
        resource_type = requirements.get("resource", "compute_instance")
        region = requirements.get("region", "us-east1")  # Default to us-east1
        security = requirements.get("security", "strict")
        
        # Format history for prompt
        history_text = self._format_chat_history(chat_history) if chat_history else "No previous conversation."
        
        if VERTEX_AI_AVAILABLE and self.model:
            if sentinel_feedback:
                # Feedback mode: Fix specific issues
                previous_code_section = f"""
**Previous Code (for reference):**
```terraform
{previous_code}
```
""" if previous_code else ""
                
                # Get specific configuration requirements
                specific_config = requirements.get("specific_config", "")
                full_user_request = requirements.get("full_user_request", scout_output if scout_output else "")
                
                specific_config_section = ""
                if specific_config:
                    specific_config_section = f"""
**CRITICAL: Specific Configuration Requirements (MUST be included):**
{specific_config}

**Full User Request (for reference):**
{full_user_request}

**IMPORTANT:** When fixing the code, ensure ALL the specific configurations mentioned above are still included. Do not remove features the user explicitly requested.
"""
                
                coder_prompt = f"""You are a DevOps Engineer. Your previous code failed validation with these errors:
{sentinel_feedback}

Rewrite the code to FIX these specific issues. Output ONLY the HCL code.

**Context:** If the user is asking for a modification, use the **History** to locate the previous code and apply the changes.

**History:**
{history_text}

{previous_code_section}
{specific_config_section}
Original Requirements: {scout_output[:200] if scout_output else f"Resource Type: {resource_type}, Region: {region}, Security Level: {security}"}

**Default Constraint:** Hardcode `region = 'us-east1'` in variables/resources unless explicitly overridden by the user. If the user does not mention a region, use `us-east1`.

**Bill of Materials (CRITICAL):** You MUST generate Terraform code ONLY for the resources explicitly listed by the Scout. Do NOT hallucinate extra resources (like Storage Buckets, Cloud SQL) unless they are strictly required for the requested resource to function. If the user didn't ask for a bucket, DO NOT add one.

**Technical Rules (MANDATORY):**
* **Firewall Linking:** If creating a firewall with `target_tags`, you MUST add the matching `tags = [...]` block to the `google_compute_instance`. The tags in the VM must exactly match the `target_tags` in the firewall.
* **Identity:** If assigning a `service_account` to a VM, you MUST create the `resource 'google_service_account' '...'` block first and reference its `.email` attribute. Do not guess the email string. Use `google_service_account.my_sa.email` or similar.
* **IAM Scopes (CRITICAL):**
    * NEVER use `cloud-platform`. This is strictly forbidden.
    * ALWAYS use specific scopes required for the task (e.g., `['logging-write', 'monitoring-write']`).
* **Networking Rules:**
    * **Private VMs:** If the user asks for a private VM (or 'no public IP'), do NOT include the `access_config` block at all. Remove it entirely. An empty block `access_config {{}}` WILL create a public IP.
    * **Firewall Sources:** Do not default to broad ranges like `0.0.0.0/0` or `10.0.0.0/8` unless explicitly necessary. Use `35.235.240.0/20` (IAP) for SSH/RDP if unsure.

**Security Rules (Apply ONLY where relevant):**
* **IF** creating Compute Instances: MUST use `shielded_instance_config`, user-managed SA, and no public IPs. NEVER use '0.0.0.0/0' for SSH/RDP. Use `var.trusted_ip_ranges`.
* **IF** creating Storage: MUST use `uniform_bucket_level_access`. Do NOT add firewall rules (storage doesn't use firewalls).
* **General:** Do NOT add unrequested resources (like subnets/firewalls) unless strictly necessary for the requested resource to function.
* **Logic Check:** Never apply firewall rules to non-compute resources (e.g., storage buckets, BigQuery datasets).
* **Output:** Return ONLY the HCL code block. No markdown text, no explanations, no code fences."""
            elif previous_code:
                # Iterative edit mode: User wants to modify existing code
                # Get specific configuration requirements
                specific_config = requirements.get("specific_config", "")
                full_user_request = requirements.get("full_user_request", scout_output if scout_output else "")
                
                specific_config_section = ""
                if specific_config:
                    specific_config_section = f"""
**CRITICAL: Specific Configuration Requirements (MUST be included):**
{specific_config}

**Full User Request (for reference):**
{full_user_request}

**IMPORTANT:** When modifying the code, ensure ALL the specific configurations mentioned above are included. Do not remove features the user explicitly requested.
"""
                
                coder_prompt = f"""Act as a DevOps Engineer. You are modifying existing Terraform code based on the user's request.

**Context:** If the user is asking for a modification, use the **History** to locate the previous code and apply the changes.

**History:**
{history_text}

**Previous Code:**
```terraform
{previous_code}
```

{specific_config_section}

**Current Request:** Modify the code above according to the user's request. If the user says "change the region to us-east1" or "update it to use us-east1", modify the region in the previous code. If they say "add encryption" or "make it secure", add the appropriate security configurations.

**Requirements:** {scout_output[:200] if scout_output else f"Resource Type: {resource_type}, Region: {region}, Security Level: {security}"}

**Default Constraint:** Hardcode `region = 'us-east1'` in variables/resources unless explicitly overridden by the user. If the user does not mention a region, use `us-east1`.

**Bill of Materials (CRITICAL):** You MUST generate Terraform code ONLY for the resources explicitly listed by the Scout. Do NOT hallucinate extra resources (like Storage Buckets, Cloud SQL) unless they are strictly required for the requested resource to function. If the user didn't ask for a bucket, DO NOT add one.

**Technical Rules (MANDATORY):**
* **Firewall Linking:** If creating a firewall with `target_tags`, you MUST add the matching `tags = [...]` block to the `google_compute_instance`. The tags in the VM must exactly match the `target_tags` in the firewall.
* **Identity:** If assigning a `service_account` to a VM, you MUST create the `resource 'google_service_account' '...'` block first and reference its `.email` attribute. Do not guess the email string. Use `google_service_account.my_sa.email` or similar.
* **IAM Scopes (CRITICAL):**
    * NEVER use `cloud-platform`. This is strictly forbidden.
    * ALWAYS use specific scopes required for the task (e.g., `['logging-write', 'monitoring-write']`).
* **Networking Rules:**
    * **Private VMs:** If the user asks for a private VM (or 'no public IP'), do NOT include the `access_config` block at all. Remove it entirely. An empty block `access_config {{}}` WILL create a public IP.
    * **Firewall Sources:** Do not default to broad ranges like `0.0.0.0/0` or `10.0.0.0/8` unless explicitly necessary. Use `35.235.240.0/20` (IAP) for SSH/RDP if unsure.

**Security Rules (Apply ONLY where relevant):**
* **IF** creating Compute Instances: MUST use `shielded_instance_config`, user-managed SA, and no public IPs. NEVER use '0.0.0.0/0' or broad internal ranges like '10.0.0.0/8' for SSH/RDP. Use a variable `var.trusted_ip_ranges`.
* **IF** creating Storage: MUST use `uniform_bucket_level_access`. Do NOT add firewall rules (storage doesn't use firewalls).
* **General:** Do NOT add unrequested resources (like subnets/firewalls) unless strictly necessary for the requested resource to function.
* **Logic Check:** Never apply firewall rules to non-compute resources (e.g., storage buckets, BigQuery datasets).

**Output:** Return ONLY the complete, updated HCL code block. No markdown text, no explanations, no code fences. Include the full code with the requested modifications."""
            else:
                # Initial generation mode
                # Get specific configuration requirements
                specific_config = requirements.get("specific_config", "")
                full_user_request = requirements.get("full_user_request", scout_output if scout_output else "")
                
                specific_config_section = ""
                if specific_config:
                    specific_config_section = f"""
**CRITICAL: Specific Configuration Requirements:**
{specific_config}

**Full User Request (for reference):**
{full_user_request}

**IMPORTANT:** You MUST include ALL the specific configurations mentioned above in your Terraform code. Do not omit any features the user explicitly requested (e.g., versioning, lifecycle rules, machine types, zones, names, etc.).
"""
                
                gke_hint = ""
                if resource_type == "gke_autopilot":
                    gke_hint = "\n**GKE Autopilot (CRITICAL):** Resource type is gke_autopilot. You MUST generate a `google_container_cluster` resource with `enable_autopilot = true`. Do NOT generate google_compute_instance or any VM.\n"
                coder_prompt = f"""Act as a DevOps Engineer. Write Terraform for: {scout_output[:200] if scout_output else f"Resource Type: {resource_type}, Region: {region}, Security Level: {security}"}.

**Context:** If the user is asking for a modification, use the **History** to locate the previous code and apply the changes.

**History:**
{history_text}

{specific_config_section}
{gke_hint}
**Default Constraint:** Hardcode `region = 'us-east1'` in variables/resources unless explicitly overridden by the user. If the user does not mention a region, use `us-east1`. Do NOT use `us-central1` or any other region as default.

**Bill of Materials (CRITICAL):** You MUST generate Terraform code ONLY for the resources explicitly listed by the Scout. Do NOT hallucinate extra resources (like Storage Buckets, Cloud SQL) unless they are strictly required for the requested resource to function. If the user didn't ask for a bucket, DO NOT add one.

**Technical Rules (MANDATORY):**
* **Firewall Linking:** If creating a firewall with `target_tags`, you MUST add the matching `tags = [...]` block to the `google_compute_instance`. The tags in the VM must exactly match the `target_tags` in the firewall.
* **Identity:** If assigning a `service_account` to a VM, you MUST create the `resource 'google_service_account' '...'` block first and reference its `.email` attribute. Do not guess the email string. Use `google_service_account.my_sa.email` or similar.
* **IAM Scopes (CRITICAL):**
    * NEVER use `cloud-platform`. This is strictly forbidden.
    * ALWAYS use specific scopes required for the task (e.g., `['logging-write', 'monitoring-write']`).
* **Networking Rules:**
    * **Private VMs:** If the user asks for a private VM (or 'no public IP'), do NOT include the `access_config` block at all. Remove it entirely. An empty block `access_config {{}}` WILL create a public IP.
    * **Firewall Sources:** Do not default to broad ranges like `0.0.0.0/0` or `10.0.0.0/8` unless explicitly necessary. Use `35.235.240.0/20` (IAP) for SSH/RDP if unsure.

**Security Rules (Apply ONLY where relevant):**
* **IF** creating Compute Instances: MUST use `shielded_instance_config`, user-managed SA, and no public IPs. NEVER use '0.0.0.0/0' or broad internal ranges like '10.0.0.0/8' for SSH/RDP. Use a variable `var.trusted_ip_ranges`.
* **IF** creating Storage: MUST use `uniform_bucket_level_access`. Do NOT add firewall rules (storage doesn't use firewalls).
* **General:** Do NOT add unrequested resources (like subnets/firewalls) unless strictly necessary for the requested resource to function.
* **Logic Check:** Never apply firewall rules to non-compute resources (e.g., storage buckets, BigQuery datasets).
* **Scope Check:** Only create the resources the user explicitly requested. If user asked for a "project", create only a project. If user asked for a "bucket", create only a bucket. Do NOT invent VMs, networks, or firewalls unless explicitly requested.

**Additional Security Requirements (where applicable):**
- NEVER use 'allUsers' or 'allAuthenticatedUsers' in IAM bindings.
- NEVER use hardcoded 'default' KMS keys; use variables or placeholders.
- Use least-privilege IAM roles and specific service accounts.
- Include proper labels, metadata, and security configurations.

**IMPORTANT: Code Formatting (CRITICAL):**
- When writing code (Terraform or Python), you MUST use proper indentation and NEWLINES.
- Do NOT minify the code. Output readable, multi-line code.
- Use proper HCL indentation (2 spaces per level).
- Add blank lines between resources and logical sections.

**Output:** Return ONLY the HCL code block. No markdown text, no explanations, no code fences.

Generate complete, production-ready Terraform HCL code that matches the user's request exactly."""
            
            prompt = coder_prompt
            
            terraform_code = self._call_gemini(prompt)
            
            if terraform_code:
                if sentinel_feedback:
                    self._log("Coder: Revised Terraform code generated.", "engineering")
                else:
                    self._log("Coder: AI-generated Terraform code complete.", "engineering")
            else:
                # Fallback to template
                terraform_code = self._generate_terraform_template(resource_type, region, security)
        else:
            # Mock mode: use template
            time.sleep(0.25)
            terraform_code = self._generate_terraform_template(resource_type, region, security)
        
        self._log("Coder: Draft complete. Sending to Sentinel.", "engineering")
        return terraform_code
    
    def _format_code(self, code: str, code_type: str = "python") -> str:
        """
        Format code to ensure proper indentation and newlines.
        Fixes minified code by adding newlines where appropriate.
        
        Args:
            code: The code to format
            code_type: Type of code ("python" or "terraform")
            
        Returns:
            Formatted code string
        """
        if not code:
            return code
        
        # Remove markdown code fences if present
        code = code.strip()
        if code.startswith("```"):
            # Remove opening fence
            lines = code.split("\n")
            if lines[0].startswith("```"):
                code = "\n".join(lines[1:])
            # Remove closing fence
            if code.endswith("```"):
                code = code[:-3].strip()
        
        # Check if code is minified (no newlines or very few)
        newline_count = code.count("\n")
        total_length = len(code)
        
        # If code is very long but has very few newlines, it's likely minified
        if total_length > 200 and newline_count < 5:
            # Try to add newlines after common patterns
            if code_type == "python":
                # Add newlines after semicolons (if present)
                code = code.replace("; ", ";\n")
                # Add newlines after common Python keywords
                code = code.replace("def ", "\ndef ")
                code = code.replace("class ", "\nclass ")
                code = code.replace("if ", "\nif ")
                code = code.replace("for ", "\nfor ")
                code = code.replace("try:", "\ntry:")
                code = code.replace("except ", "\nexcept ")
                code = code.replace("import ", "\nimport ")
                code = code.replace("from ", "\nfrom ")
            elif code_type == "terraform":
                # Add newlines after Terraform resource blocks
                code = code.replace("resource \"", "\nresource \"")
                code = code.replace("variable \"", "\nvariable \"")
                code = code.replace("output \"", "\noutput \"")
                code = code.replace("provider \"", "\nprovider \"")
                code = code.replace("  {", " {\n")
                code = code.replace("  }", "\n  }\n")
        
        # Clean up multiple consecutive newlines
        code = re.sub(r'\n{3,}', '\n\n', code)
        
        return code.strip()
    
    def _generate_python_template(self, purpose: str, gcp_service: str) -> str:
        """Generate Python script template (fallback when AI is unavailable)."""
        if purpose == "list_all_vm_instances" or gcp_service == "compute_engine_api":
            return '''#!/usr/bin/env python3
"""
List all VM instances in a Google Cloud Project.
"""

from google.cloud import compute_v1
from google.auth import default
import sys

def list_all_instances(project_id: str):
    """List all VM instances in the project."""
    try:
        # Authenticate using Application Default Credentials
        credentials, project = default()
        
        # Use provided project_id or default
        if not project_id:
            project_id = project
        
        if not project_id:
            print("Error: Project ID is required.")
            print("Set GOOGLE_CLOUD_PROJECT environment variable or provide project_id.")
            sys.exit(1)
        
        # Initialize Compute Engine client
        instance_client = compute_v1.InstancesClient(credentials=credentials)
        
        # List all zones
        zones_client = compute_v1.ZonesClient(credentials=credentials)
        zones = zones_client.list(project=project_id)
        
        instances_found = False
        
        # Iterate through all zones
        for zone in zones:
            zone_name = zone.name
            
            # List instances in this zone
            instances = instance_client.list(project=project_id, zone=zone_name)
            
            for instance in instances:
                instances_found = True
                print(f"Instance: {instance.name}")
                print(f"  Zone: {zone_name}")
                print(f"  Machine Type: {instance.machine_type.split('/')[-1]}")
                print(f"  Status: {instance.status}")
                print(f"  Internal IP: {instance.network_interfaces[0].network_i_p if instance.network_interfaces else 'N/A'}")
                print("-" * 50)
        
        if not instances_found:
            print(f"No VM instances found in project: {project_id}")
    
    except Exception as e:
        print(f"Error listing instances: {e}")
        sys.exit(1)

if __name__ == "__main__":
    import os
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    list_all_instances(project_id)'''
        elif purpose == "list_storage_blobs" or gcp_service == "storage_api":
            return '''#!/usr/bin/env python3
"""
List all files (blobs) in a Google Cloud Storage bucket.
"""

from google.cloud import storage
from google.auth import default
import sys

def list_blobs(bucket_name: str, project_id: str = None):
    """List all blobs in the specified bucket."""
    try:
        # Authenticate using Application Default Credentials
        credentials, project = default()
        
        # Use provided project_id or default
        if not project_id:
            project_id = project
        
        if not bucket_name:
            print("Error: Bucket name is required.")
            sys.exit(1)
        
        # Initialize Storage client
        client = storage.Client(credentials=credentials, project=project_id)
        
        # Get the bucket
        bucket = client.bucket(bucket_name)
        
        # List all blobs
        blobs = bucket.list_blobs()
        
        blob_count = 0
        for blob in blobs:
            blob_count += 1
            print(f"Blob: {blob.name}")
            print(f"  Size: {blob.size} bytes")
            print(f"  Content Type: {blob.content_type}")
            print(f"  Created: {blob.time_created}")
            print("-" * 50)
        
        if blob_count == 0:
            print(f"No blobs found in bucket: {bucket_name}")
        else:
            print(f"Total blobs: {blob_count}")
    
    except Exception as e:
        print(f"Error listing blobs: {e}")
        sys.exit(1)

if __name__ == "__main__":
    import os
    bucket_name = os.getenv("BUCKET_NAME") or input("Enter bucket name: ")
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    list_blobs(bucket_name, project_id)'''
        elif purpose == "publish_message" or gcp_service == "pubsub_api":
            return '''#!/usr/bin/env python3
"""
Publish a message to a Google Cloud Pub/Sub topic.
"""

from google.cloud import pubsub_v1
from google.auth import default
import sys

def publish_message(project_id: str, topic_name: str, message: str):
    """Publish a message to the specified Pub/Sub topic."""
    try:
        # Authenticate using Application Default Credentials
        credentials, project = default()
        
        # Use provided project_id or default
        if not project_id:
            project_id = project
        
        if not project_id or not topic_name:
            print("Error: Project ID and topic name are required.")
            sys.exit(1)
        
        # Initialize Publisher client
        publisher = pubsub_v1.PublisherClient(credentials=credentials)
        
        # Construct topic path
        topic_path = publisher.topic_path(project_id, topic_name)
        
        # Publish the message
        future = publisher.publish(topic_path, message.encode('utf-8'))
        message_id = future.result()
        
        print(f"Message published successfully!")
        print(f"  Topic: {topic_name}")
        print(f"  Message ID: {message_id}")
        print(f"  Message: {message}")
    
    except Exception as e:
        print(f"Error publishing message: {e}")
        sys.exit(1)

if __name__ == "__main__":
    import os
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    topic_name = os.getenv("TOPIC_NAME") or input("Enter topic name: ")
    message = os.getenv("MESSAGE") or "Hello World"
    publish_message(project_id, topic_name, message)'''
        else:
            return '''#!/usr/bin/env python3
"""
Python script for Google Cloud Platform operations.
"""

from google.auth import default
import sys

def main():
    """Main function."""
    try:
        # Authenticate using Application Default Credentials
        credentials, project = default()
        print(f"Authenticated with project: {project}")
        # Add your GCP operations here
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()'''
    
    def _generate_terraform_template(self, resource_type: str, region: str, security: str) -> str:
        """Generate Terraform template (fallback when AI is unavailable)."""
        if resource_type == "compute_instance":
            return f'''resource "google_compute_instance" "default" {{
  name         = "ai-agent-instance"
  machine_type = "e2-medium"
  zone         = "{region}-a"

  boot_disk {{
    initialize_params {{
      image = "debian-cloud/debian-11"
      size  = 20
    }}
  }}

  network_interface {{
    network = "default"
    // No access_config = private VM (no public IP)
  }}

  labels = {{
    environment = "production"
    managed-by  = "ai-agent-prism"
  }}

  metadata = {{
    enable-oslogin = "TRUE"
  }}
}}'''
        elif resource_type == "storage_bucket":
            return f'''resource "google_storage_bucket" "default" {{
  name          = "ai-agent-bucket-{int(time.time())}"
  location      = "{region}"
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {{
    enabled = true
  }}

  labels = {{
    environment = "production"
    managed-by  = "ai-agent-prism"
  }}
}}'''
        elif resource_type == "compute_network":
            return f'''resource "google_compute_network" "default" {{
  name                    = "ai-agent-network"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  labels = {{
    environment = "production"
    managed-by  = "ai-agent-prism"
  }}
}}'''
        elif resource_type == "gke_autopilot":
            return f'''resource "google_container_cluster" "primary" {{
  name     = "ai-agent-autopilot-cluster"
  location = "{region}"

  enable_autopilot = true

  release_channel {{
    channel = "REGULAR"
  }}

  labels = {{
    environment = "production"
    managed-by  = "ai-agent-prism"
  }}
}}'''
        else:
            return f'''resource "google_compute_instance" "default" {{
  name         = "ai-agent-instance"
  machine_type = "e2-medium"
  zone         = "{region}-a"

  boot_disk {{
    initialize_params {{
      image = "debian-cloud/debian-11"
    }}
  }}

  network_interface {{
    network = "default"
  }}
}}'''
    
    def _requirements_qa_agent(self, user_request: str, requirements: Dict[str, str], execution_logs: list = None) -> Tuple[bool, str]:
        """
        Requirements QA Agent: Checks whether Scout's requirements correctly capture user intent.
        Returns (passed: bool, feedback: str). When passed is False, feedback is used to re-Scout.
        """
        if execution_logs is not None:
            execution_logs.append("📋 Requirements QA: Checking if requirements match user intent...")
        self._log("Requirements QA: Checking if requirements match user intent...", "engineering")
        if not VERTEX_AI_AVAILABLE or not self.model:
            if execution_logs is not None:
                execution_logs.append("📋 Requirements QA: Skipped (no model).")
            return (True, "")
        resource = requirements.get("resource", "")
        output_type = requirements.get("output_type", "")
        prompt = f"""You are a QA checker. The user made this request: "{user_request[:400]}"

The system produced these requirements: output_type={output_type}, resource={resource}.

Do these requirements correctly capture what the user asked for?
- If the user asked for GKE / Autopilot / Kubernetes cluster and resource is NOT gke_autopilot (e.g. it is compute_instance), say FAIL and in one sentence say what is wrong (e.g. "User asked for GKE Autopilot but requirements say compute_instance. Set resource to gke_autopilot.").
- If the user asked for something else and the resource/output_type clearly do not match, say FAIL with one sentence feedback.
- Otherwise say PASS.

**Output (exactly one line):**
Either: PASS
Or: FAIL: <one sentence feedback>"""
        try:
            response = self._call_gemini(prompt)
            if not response:
                if execution_logs is not None:
                    execution_logs.append("📋 Requirements QA: No response, assuming pass.")
                return (True, "")
            response_upper = response.strip().upper()
            if "PASS" in response_upper and "FAIL" not in response_upper[:10]:
                if execution_logs is not None:
                    execution_logs.append("✅ Requirements QA: Passed. Requirements match user intent.")
                self._log("Requirements QA: Passed.", "engineering")
                return (True, "")
            feedback = response.strip()
            for prefix in ("FAIL:", "FAIL :", "FAIL："):
                if prefix.upper() in response_upper:
                    idx = response_upper.find(prefix.upper())
                    feedback = response[idx + len(prefix):].strip()
                    break
            if execution_logs is not None:
                execution_logs.append(f"📋 Requirements QA: Failed. {feedback[:120]}...")
            self._log(f"Requirements QA: Failed. {feedback[:120]}", "engineering")
            return (False, feedback)
        except Exception as e:
            if execution_logs is not None:
                execution_logs.append(f"📋 Requirements QA: Error ({e}), assuming pass.")
            return (True, "")
    
    def _output_qa_agent(self, user_request: str, output_content: str, output_type: str, execution_logs: list = None) -> Tuple[bool, str]:
        """
        Output QA Agent: Sanity check that the generated output actually addresses the user's question.
        Detects hallucination, off-topic answers, or answers that don't align with the question.
        Used for Terraform, architectural explanations, and Python scripts.
        Returns (passed: bool, feedback: str). feedback is for the Coder when passed is False.
        """
        if execution_logs is not None:
            execution_logs.append("📋 Output QA: Checking if output aligns with user question (sanity check)...")
        self._log("Output QA: Checking if output aligns with user question (sanity check)...", "engineering")
        if not VERTEX_AI_AVAILABLE or not self.model:
            if execution_logs is not None:
                execution_logs.append("📋 Output QA: Skipped (no model).")
            return (True, "")
        prompt = f"""You are a QA sanity checker. Your job is to verify: Does this output actually address the user's question, or did the agent hallucinate / answer something else / go off-topic?

**User question:** {user_request[:500]}

**Generated output (type: {output_type}):**
{output_content[:3500]}

**Rules:**
- If the output directly and correctly answers the user's question (or implements what they asked for), say PASS.
- If the output is off-topic, hallucinates facts, answers a different question, or does not align with what the user asked, say FAIL and give one short sentence of feedback (e.g. what is wrong or what to fix).
- For Terraform: If the user asked for GKE/Autopilot but the code creates google_compute_instance, say FAIL.
- For explanations: If the user asked "what is the least-privilege role for X?" and the answer talks about something else or doesn't address least-privilege for X, say FAIL.

**Output (exactly one line):**
Either: PASS
Or: FAIL: <one sentence feedback>"""
        try:
            response = self._call_gemini(prompt)
            if not response:
                if execution_logs is not None:
                    execution_logs.append("📋 Output QA: No response, assuming pass.")
                return (True, "")
            response_upper = response.strip().upper()
            if "PASS" in response_upper and "FAIL" not in response_upper[:10]:
                if execution_logs is not None:
                    execution_logs.append("✅ Output QA: Passed. Output aligns with user question.")
                self._log("Output QA: Passed.", "engineering")
                return (True, "")
            # Extract feedback after "FAIL:" or "FAIL :"
            feedback = response.strip()
            for prefix in ("FAIL:", "FAIL :", "FAIL："):
                if prefix.upper() in response_upper:
                    idx = response_upper.find(prefix.upper())
                    feedback = response[idx + len(prefix):].strip()
                    break
            if execution_logs is not None:
                execution_logs.append(f"📋 Output QA: Failed. {feedback[:120]}...")
            self._log(f"Output QA: Failed. {feedback[:120]}", "engineering")
            return (False, f"Output QA: {feedback}")
        except Exception as e:
            if execution_logs is not None:
                execution_logs.append(f"📋 Output QA: Error ({e}), assuming pass.")
            return (True, "")
    
    def _sentinel_agent(self, code: str, user_request: str, output_type: str = "terraform", execution_logs: list = None) -> Tuple[bool, str]:
        """
        Sentinel Agent: Validates code for security vulnerabilities using Vertex AI.
        
        Args:
            code: The code to validate (Terraform or Python)
            user_request: Original user request (to check for "insecure" keyword)
            output_type: Type of code ("terraform" or "python_script")
            
        Returns:
            Tuple of (is_valid: bool, message: str)
        """
        # Python script validation
        if output_type == "python_script":
            log_msg = "🛡️ Sentinel: Validating Python script security..."
            self._log("Sentinel: Validating Python script security...", "engineering")
            if execution_logs is not None:
                execution_logs.append(log_msg)
            
            # Basic Python security checks
            security_issues = []
            
            # Check for hardcoded secrets
            if "password" in code.lower() or "api_key" in code.lower() or "secret" in code.lower():
                if '"' in code or "'" in code:  # Only flag if it looks like a hardcoded value
                    security_issues.append("Potential hardcoded secrets detected")
            
            # Check for insecure practices
            if "eval(" in code or "exec(" in code:
                security_issues.append("Use of eval() or exec() detected - potential security risk")
            
            # Check for insecure HTTP requests
            if "http://" in code and "https://" not in code:
                security_issues.append("Insecure HTTP requests detected - prefer HTTPS")
            
            if security_issues:
                log_msg = f"🔄 Sentinel: Python script validation failed. {', '.join(security_issues)}"
                self._log(f"Sentinel: Python script validation failed. {', '.join(security_issues)}", "engineering")
                if execution_logs is not None:
                    execution_logs.append(log_msg)
                return (False, f"SECURITY ALERT: {', '.join(security_issues)}")
            
            log_msg = "🛡️ Sentinel: Scan passed."
            self._log("Sentinel: Python script validation passed.", "engineering")
            if execution_logs is not None:
                execution_logs.append(log_msg)
            return (True, "Python script validation passed. Review code before execution.")
        
        # Terraform validation
        log_msg = "🔒 Sentinel: Scanning for security vulnerabilities..."
        self._log("Sentinel: Scanning for security vulnerabilities...", "engineering")
        if execution_logs is not None:
            execution_logs.append(log_msg)
        
        # Skip validation for architectural explanations (they're plain text, not code)
        if output_type == "architectural_explanation":
            self._log("Sentinel: Architectural explanation detected. Skipping code validation.", "engineering")
            return (True, "Architectural advice approved. No code validation needed.")
        
        # Additional check: If code doesn't contain code blocks or Terraform syntax, it's likely an explanation
        if output_type != "terraform" and "```" not in code and not code.strip().startswith("resource") and not code.strip().startswith("provider"):
            self._log("Sentinel: Plain text explanation detected. Skipping code validation.", "engineering")
            return (True, "Text explanation approved. No code validation needed.")
        
        # Always check for explicit "insecure" keyword first
        if "insecure" in user_request.lower():
            self._log("Sentinel: Validation Failed. Security vulnerabilities detected.", "engineering")
            return (False, "SECURITY ALERT: Code rejected due to insecure configuration request.")
        
        if VERTEX_AI_AVAILABLE and self.model:
            SENTINEL_SYSTEM_PROMPT = """
You are "The Sentinel," the final quality assurance and security gatekeeper for the Prism Engineering Department.
Your job is to AUDIT Terraform code generated by "The Coder."

You have two distinct responsibilities:
1. SECURITY (The "No" Man): Block overly permissive roles (Owner/Editor) and public access.
2. SYNTAX (The Compiler): Catch common hallucinated arguments in Google Cloud resources.

### CRITICAL SYNTAX RULES (Use this checklist):
- **Cloud Functions Gen 2 (`google_cloudfunctions2_function`):**
  - ERROR TRAP: Do NOT allow nested `vpc_connector { ... }` blocks.
  - CORRECTION: `vpc_connector` must be a direct string argument inside `service_config`.
  - ERROR TRAP: Do NOT allow `roles/cloudfunctions.invoker` to be granted to the function's OWN service account. (Self-invocation is useless).

### HALLUCINATION GUARDRAILS:
1. **Evidence required:** You must cite the specific line number or resource name that violates a rule.
2. **No Phantom Errors:** Do NOT flag "Scope Creep" unless you see a resource (like `google_storage_bucket`) that is completely unrelated to the user's request.
3. **Verify Defaults:** Do not block code for including default-enabled features (like Workload Identity in Autopilot).

### OUTPUT FORMAT:
Status: [APPROVED | BLOCKED]
Feedback: [Specific, actionable technical feedback. Do NOT repeat generic examples.]
"""
            
            prompt = f"""{SENTINEL_SYSTEM_PROMPT}

**Input:** User Request: "{user_request}" | Code: 
```terraform
{code}
```

**Additional Validation Steps:**

1. **Scope Check (CRITICAL):** Does the code do *exactly* what the user asked?
   * If the user asked for a Project but the code creates a VM, Fail with: 'BLOCKED: Scope Creep. User did not ask for a VM.'
   * If the user asked for a Storage Bucket but the code creates a Compute Instance, Fail with: 'BLOCKED: Scope Creep. User did not ask for a Compute Instance.'
   * Only create resources that match the user's explicit request.

2. **Logic Check:** Are the resources compatible?
   * If code adds a `google_compute_firewall` for a `google_storage_bucket` request, Fail with: 'BLOCKED: Hallucination. Cannot apply firewall to bucket. Firewalls are for compute resources only.'
   * If code adds compute-specific security (shielded_instance_config) to a storage bucket, Fail with: 'BLOCKED: Hallucination. Shielded VM config only applies to compute instances.'
   * If code adds network rules to non-network resources (BigQuery, Storage, etc.), Fail with: 'BLOCKED: Hallucination. Network rules do not apply to this resource type.'

3. **Security Check:** Audit the *existing* resources for vulnerabilities:
   * **Verification Rule:** Before flagging an error, you MUST verify it exists in the code text.
     * *Example:* Do not say 'Invalid Scope: cloud-platform' unless the string `cloud-platform` actually appears in the `scopes = [...]` list.
     * If the code uses specific scopes (like `logging-write`), DO NOT flag it as overly permissive.
   * Hardcoded secrets or credentials
   * Overly permissive access controls (0.0.0.0/0, allUsers, cloud-platform scope) - **ONLY if actually present in code**
   * **IAM Scopes:** Reject any code using `scopes = ["cloud-platform"]` - **ONLY if this exact string appears in the code**
   * **IAM Roles:** Block overly permissive roles (Owner, Editor) - use Viewer or custom roles instead
   * **Public Access:** Block public access to sensitive resources (allUsers, allAuthenticatedUsers)
   * **Public IP Exposure:** Reject code with empty `access_config {{}}` blocks that create unintended public IPs. For private VMs, the `access_config` block must be completely absent.
   * Missing security best practices (encryption, IAM, labels)
   * Public exposure of sensitive resources
   * Missing encryption or security labels

**Output Format (STRICT):**
* If the code is secure and valid: Output `Status: APPROVED` followed by `Feedback: "Security and Syntax checks passed."`
* If invalid: Output `Status: BLOCKED` followed by `Feedback:` and a bulleted list of SPECIFIC technical errors.

Be strict and specific. Reject code that has scope creep, logical errors, or syntax issues."""
            
            response = self._call_gemini(prompt)
            
            if response:
                response_upper = response.strip().upper()
                # Check for new format: "Status: APPROVED" or "Status: BLOCKED"
                if "STATUS: APPROVED" in response_upper or response_upper == "SECURE":
                    log_msg = "✅ Sentinel: Validation Passed. Code is secure."
                    self._log("Sentinel: Validation Passed. Code is secure.", "engineering")
                    if execution_logs is not None:
                        execution_logs.append(log_msg)
                    return (True, "Code validated successfully. Ready for deployment.")
                elif "STATUS: BLOCKED" in response_upper or response_upper.startswith("INVALID"):
                    # Extract the error message after "Status: BLOCKED" or "INVALID:"
                    if "FEEDBACK:" in response_upper:
                        # New format: extract feedback section
                        feedback_start = response.upper().find("FEEDBACK:")
                        error_msg = response[feedback_start + len("FEEDBACK:"):].strip()
                    elif ":" in response:
                        # Old format: extract after "INVALID:"
                        error_msg = response[response.find(":") + 1:].strip()
                    else:
                        error_msg = response
                    log_msg = f"🔄 Sentinel: Validation Failed. {error_msg[:100]}..."
                    self._log(f"Sentinel: Validation Failed. {error_msg[:100]}...", "engineering")
                    if execution_logs is not None:
                        execution_logs.append(log_msg)
                    return (False, f"SECURITY ALERT: {error_msg}")
                else:
                    # If response doesn't match expected format, treat as invalid
                    self._log(f"Sentinel: Validation Failed. Unexpected response format: {response[:100]}...", "engineering")
                    return (False, f"SECURITY ALERT: Validation response format error. Expected 'Status: APPROVED' or 'Status: BLOCKED', got: {response[:200]}")
            else:
                # Fallback: basic validation
                return self._basic_validation(code)
        else:
            # Mock mode: basic validation
            time.sleep(0.25)
            return self._basic_validation(code)
    
    def _basic_validation(self, terraform_code: str) -> Tuple[bool, str]:
        """Basic validation fallback when AI is unavailable."""
        security_issues = []
        
        # Check for hardcoded secrets
        if "password" in terraform_code.lower() or "secret" in terraform_code.lower():
            security_issues.append("Potential hardcoded secrets detected")
        
        if security_issues:
            self._log(f"Sentinel: Validation Failed. Issues: {', '.join(security_issues)}", "engineering")
            return (False, f"SECURITY ALERT: Code rejected. {', '.join(security_issues)}")
        
        self._log("Sentinel: Validation Passed. Code is secure.", "engineering")
        return (True, "Code validated successfully. Ready for deployment.")
    
    def run(self, user_request: str, conversation_turn: int = 0, chat_history: list = None) -> Tuple[bool, dict]:
        """
        Execute the Engineering Pipeline workflow with self-healing retry mechanism.
        
        Args:
            user_request: The user's engineering request
            conversation_turn: Current conversation turn number
            chat_history: List of previous messages in format [{"role": "user|assistant", "content": "..."}, ...]
            
        Returns:
            Tuple of (success: bool, result_dict: dict)
            - If successful: (True, {"code": code, "cost": cost_analysis, "logs": execution_logs})
            - If failed after max retries: (True, {"code": draft_code_with_warning, "cost": cost_analysis, "logs": execution_logs})
            - If failed with error: (False, {"code": error_message, "logs": execution_logs})
        """
        self.conversation_turn = conversation_turn
        self.user_input = user_request
        
        # Initialize execution logs
        execution_logs = []
        
        # Default to empty history if not provided
        if chat_history is None:
            chat_history = []
        
        try:
            # Step 0: Check Memory First
            execution_logs.append("🟢 Engineering: Checking memory for cached solution...")
            cached_solution = memory.get_solution(user_request)
            if cached_solution:
                cached_code, cached_explanation = cached_solution
                execution_logs.append("🧠 Memory: Solution found in cache. Skipping agents.")
                self._log("🧠 Memory: Solution found in cache. Skipping agents.", "memory")
                # Return cached solution with logs
                if isinstance(cached_code, str):
                    return (True, {"code": cached_code, "cost": None, "logs": execution_logs})
                else:
                    # If cached_code is already a dict, add logs to it
                    if isinstance(cached_code, dict):
                        cached_code["logs"] = execution_logs
                        return (True, cached_code)
                    return (True, {"code": str(cached_code), "cost": None, "logs": execution_logs})
            
            # Step 1: Scout - Gather requirements (only once, with context)
            requirements = self._scout_agent(user_request, chat_history, execution_logs)
            output_type = requirements.get("output_type", "terraform")
            execution_logs.append(f"🟢 Scout: Output type determined: {output_type}.")
            
            # Step 1b: Requirements QA - Do requirements match user intent? (Terraform path; one retry)
            if output_type == "terraform":
                req_qa_passed, req_qa_feedback = self._requirements_qa_agent(user_request, requirements, execution_logs)
                if not req_qa_passed:
                    execution_logs.append("🔄 Requirements QA: Re-running Scout with correction hint...")
                    self._log("Requirements QA: Re-running Scout with correction hint...", "engineering")
                    requirements = self._scout_agent(
                        req_qa_feedback + "\n\nOriginal user request: " + user_request,
                        chat_history,
                        execution_logs,
                    )
                    output_type = requirements.get("output_type", "terraform")
                    execution_logs.append(f"🟢 Scout: Output type after correction: {output_type}.")
            else:
                execution_logs.append("📋 Requirements QA: Skipped (only run for Terraform).")
            
            if output_type == "architectural_explanation":
                # Architectural explanation: Coder -> Output QA (sanity check) -> return
                scout_output = f"Question Type: {requirements.get('question_type')}, Topics: {requirements.get('topics')}"
                explanation = self._coder_agent(requirements, scout_output, sentinel_feedback="", previous_code="", chat_history=chat_history, execution_logs=execution_logs)
                qa_passed, qa_feedback = self._output_qa_agent(user_request, explanation, "architectural_explanation", execution_logs)
                if not qa_passed:
                    execution_logs.append("🔄 Output QA: Retrying Coder with feedback...")
                    explanation = self._coder_agent(
                        requirements,
                        scout_output,
                        sentinel_feedback=qa_feedback,
                        previous_code=explanation,
                        chat_history=chat_history,
                        execution_logs=execution_logs,
                    )
                    qa_passed_2, _ = self._output_qa_agent(user_request, explanation, "architectural_explanation", execution_logs)
                    if not qa_passed_2:
                        execution_logs.append("⚠️ Output QA: Still misaligned after retry; returning best effort.")
                execution_logs.append("✅ Architectural explanation generated successfully.")
                self._log("✅ Architectural explanation generated successfully.", "engineering")
                return (True, {"code": explanation, "cost": None, "logs": execution_logs})
            
            if output_type == "python_script":
                # Python script: Coder -> Output QA (sanity check) -> Sentinel
                scout_output = f"Purpose: {requirements.get('purpose')}, GCP Service: {requirements.get('gcp_service')}"
                python_code = self._coder_agent(requirements, scout_output, sentinel_feedback="", previous_code="", chat_history=chat_history, execution_logs=execution_logs)
                python_code = self._format_code(python_code, "python")
                qa_passed, qa_feedback = self._output_qa_agent(user_request, python_code, "python_script", execution_logs)
                if not qa_passed:
                    execution_logs.append("🔄 Output QA: Retrying Coder with feedback...")
                    python_code = self._coder_agent(requirements, scout_output, sentinel_feedback=qa_feedback, previous_code=python_code, chat_history=chat_history, execution_logs=execution_logs)
                    python_code = self._format_code(python_code, "python")
                    self._output_qa_agent(user_request, python_code, "python_script", execution_logs)
                
                # Step: Sentinel - Validate Python script
                is_valid, validation_message = self._sentinel_agent(python_code, user_request, output_type="python_script", execution_logs=execution_logs)
                
                if is_valid:
                    execution_logs.append("✅ Python script generated and validated successfully.")
                    self._log("✅ Python script generated and validated successfully.", "engineering")
                else:
                    execution_logs.append(f"⚠️ Python script generated but validation found issues: {validation_message[:100]}")
                    self._log(f"⚠️ Python script validation found issues: {validation_message[:100]}", "engineering")
                
                # Return Python code (no cost analysis for scripts)
                return (True, {"code": python_code, "cost": None, "logs": execution_logs})
            
            # Terraform generation flow (existing logic)
            scout_output = f"Resource: {requirements.get('resource')}, Region: {requirements.get('region')}, Security: {requirements.get('security')}"
            execution_logs.append(f"🟢 Scout: Resource type: {requirements.get('resource')}, Region: {requirements.get('region')}, Security: {requirements.get('security')}")
            
            # Step 2, 2b, 3: Self-Healing Retry Loop (Coder -> Output QA -> Sentinel)
            max_retries = 3
            terraform_code = None
            last_validation_message = ""
            
            # Extract previous Terraform code from history if available
            previous_code = self._extract_previous_code(chat_history)
            if previous_code:
                execution_logs.append("🟢 Coder: Found previous code in conversation history.")
            
            for attempt in range(1, max_retries + 1):
                # Step 2: Coder - Generate or regenerate Terraform code
                if attempt == 1:
                    # First attempt: initial generation (with previous code if available)
                    terraform_code = self._coder_agent(requirements, scout_output, sentinel_feedback="", previous_code=previous_code, chat_history=chat_history, execution_logs=execution_logs)
                    # Format code if needed (fix minified code)
                    terraform_code = self._format_code(terraform_code, "terraform")
                    execution_logs.append("🟢 Coder: Terraform code generated.")
                else:
                    # Retry attempts: regenerate with feedback (from Output QA or Sentinel)
                    execution_logs.append(f"🔄 Coder: Retry attempt {attempt}/{max_retries} based on feedback...")
                    self._log(f"🔄 Coder: Retry attempt {attempt}/{max_retries}...", "engineering")
                    terraform_code = self._coder_agent(requirements, scout_output, last_validation_message, previous_code=previous_code, chat_history=chat_history, execution_logs=execution_logs)
                    # Format code if needed (fix minified code)
                    terraform_code = self._format_code(terraform_code, "terraform")
                    execution_logs.append(f"🟢 Coder: Revised Terraform code generated (attempt {attempt}).")
                
                # Step 2b: Output QA - Does the code match the user request?
                qa_passed, qa_feedback = self._output_qa_agent(user_request, terraform_code, "terraform", execution_logs)
                if not qa_passed:
                    last_validation_message = qa_feedback
                    execution_logs.append(f"🔄 Output QA: Correctness check failed (attempt {attempt}/{max_retries}). Sending feedback to Coder...")
                    self._log(f"🔄 Output QA: Correctness check failed. Sending feedback to Coder...", "engineering")
                    if attempt == max_retries:
                        break
                    continue
                
                # Step 3: Sentinel - Validate code (security)
                is_valid, validation_message = self._sentinel_agent(terraform_code, user_request, output_type="terraform", execution_logs=execution_logs)
                
                if is_valid:
                    # Success: Code approved
                    execution_logs.append("✅ Sentinel: Code validation passed. Security checks complete.")
                    self._log("✅ Sentinel: Code approved.", "engineering")
                    
                    # Save secure solution to memory
                    execution_logs.append("💾 Memory: Saving validated solution to cache...")
                    memory.save_solution(user_request, terraform_code, validation_message)
                    execution_logs.append("💾 Memory: Solution saved to database.")
                    self._log("💾 Memory: Secure solution saved to database.", "memory")
                    
                    # Return dictionary with code and logs (no cost analysis)
                    return (True, {"code": terraform_code, "cost": None, "logs": execution_logs})
                else:
                    # Validation failed: prepare feedback for next attempt
                    last_validation_message = validation_message
                    execution_logs.append(f"🔄 Sentinel: Validation failed (attempt {attempt}/{max_retries}). Issues: {validation_message[:100]}...")
                    self._log(f"🔄 Sentinel: Issues found (attempt {attempt}/{max_retries}). Sending feedback to Coder...", "engineering")
                    
                    # If this was the last attempt, break to fallback
                    if attempt == max_retries:
                        break
            
            # Fallback: Max retries reached - return draft code with warning
            execution_logs.append(f"⚠️ Sentinel: Max retries ({max_retries}) reached. Publishing DRAFT code with warnings.")
            self._log("⚠️ Sentinel: Max retries reached. Publishing DRAFT code with warnings.", "engineering")
            
            # Wrap code in warning block (Markdown format)
            draft_code_with_warning = f"""> **⚠️ WARNING: Security checks failed after {max_retries} attempts.**

> **Last validation errors:**
> {last_validation_message}

> **This code has NOT been saved to memory and may contain security vulnerabilities.**
> **Review carefully before deployment.**

```terraform
{terraform_code}
```"""
            
            # Return as "success" but with warning (so user sees the code)
            # Do NOT save to memory
            
            return (True, {"code": draft_code_with_warning, "cost": None, "logs": execution_logs})
                
        except Exception as e:
            error_msg = f"Pipeline Error: {str(e)}"
            execution_logs.append(f"🚨 Engineering: Error in pipeline - {error_msg}")
            self._log(error_msg, "engineering")
            return (False, {"code": error_msg, "logs": execution_logs})
