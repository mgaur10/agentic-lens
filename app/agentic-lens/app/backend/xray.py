import os
import re
import vertexai
from vertexai.preview.generative_models import GenerativeModel


def _init_vertex():
    """Initialize Vertex AI; prefer GCP_PROJECT_ID (string id) over GOOGLE_CLOUD_PROJECT."""
    project_id = (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
    location = (os.getenv("GCP_LOCATION") or "us-west1").strip()
    if project_id:
        vertexai.init(project=project_id, location=location)


class XRayAgent:
    def __init__(self):
        _init_vertex()
        model_version = os.getenv("MODEL_VERSION", "gemini-2.5-pro")
        self.model = GenerativeModel(model_version)
    
    def answer(self, query: str, history: list = None):
        # 1. Glass Box: Start Scan
        logs = ["🦴 X-Ray: Initiating Deep Code Analysis...", "🔦 X-Ray: Scanning for IAM Patterns..."]
        
        # 2. System Prompt for Least Privilege Analysis
        system_instruction = """
        You are the 'X-Ray' Agent (Department: Security & Audit).
        Your ONE goal is to enforce "Least Privilege" security on Google Cloud code.
        
        When the user provides code (Terraform, Python, Docker) or a GitHub link:
        1. **IDENTIFY:** List every GCP resource and API method used (e.g., `google_storage_bucket`, `pubsub.create`).
        2. **CONTRAST:**
           - **⚠️ Lazy Way:** What Role would a lazy developer ask for? (e.g., `roles/storage.admin`). Explain why it's bad.
           - **✅ X-Ray Way:** What are the EXACT Granular Permissions needed? (e.g., `storage.buckets.create`).
        3. **PRESCRIBE:** Generate the `gcloud iam roles create` command to build a Custom Role for this specific workload.
        
        Tone: Clinical, Precise, Authoritative. Use emojis: 🦴, 🔦, 🛡️.
        """
        
        # 3. Call Gemini
        chat = self.model.start_chat()
        response = chat.send_message(f"{system_instruction}\n\nUSER QUERY: {query}")
        
        # 4. Glass Box: Complete Scan
        logs.append("🛡️ X-Ray: Least Privilege Matrix Generated.")
        
        return {"answer": response.text, "logs": logs}
