"""
GCP Secret Manager Integration
Handles retrieval of sensitive data from GCP Secret Manager.
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables for GCP project config
load_dotenv()

try:
    from google.cloud import secretmanager
    SECRET_MANAGER_AVAILABLE = True
except ImportError:
    SECRET_MANAGER_AVAILABLE = False
    print("⚠️  google-cloud-secret-manager not installed. Install with: pip install google-cloud-secret-manager")


class SecretManager:
    """
    Utility class for accessing GCP Secret Manager.
    Falls back to environment variables if Secret Manager is unavailable.
    """
    
    def __init__(self, project_id: Optional[str] = None):
        """
        Initialize Secret Manager client.
        
        Args:
            project_id: GCP Project ID. If None, reads from GCP_PROJECT_ID env var.
        """
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        self.client = None
        
        if SECRET_MANAGER_AVAILABLE and self.project_id:
            try:
                self.client = secretmanager.SecretManagerServiceClient()
            except Exception as e:
                print(f"⚠️  Failed to initialize Secret Manager client: {e}")
                print("   Falling back to environment variables.")
                self.client = None
        else:
            if not SECRET_MANAGER_AVAILABLE:
                print("⚠️  Secret Manager SDK not available. Using environment variables.")
            if not self.project_id:
                print("⚠️  GCP_PROJECT_ID not set. Using environment variables.")
    
    def get_secret(self, secret_id: str, version: str = "latest") -> Optional[str]:
        """
        Retrieve a secret from Secret Manager.
        
        Args:
            secret_id: The secret ID (name) in Secret Manager
            version: Secret version (default: "latest")
            
        Returns:
            Secret value as string, or None if not found
        """
        # Try Secret Manager first
        if self.client and self.project_id:
            try:
                name = f"projects/{self.project_id}/secrets/{secret_id}/versions/{version}"
                response = self.client.access_secret_version(request={"name": name})
                return response.payload.data.decode("UTF-8")
            except Exception as e:
                print(f"⚠️  Failed to retrieve secret '{secret_id}' from Secret Manager: {e}")
                print(f"   Falling back to environment variable: {secret_id.upper()}")
        
        # Fallback to environment variable
        env_key = secret_id.upper().replace("-", "_")
        return os.getenv(env_key)
    
    @staticmethod
    def create_secret_instructions() -> str:
        """Return instructions for creating secrets in Secret Manager."""
        return """
To store secrets in GCP Secret Manager, use the following commands:

   gcloud secrets create SECRET_NAME \\
       --data-file=- \\
       --project=YOUR_PROJECT_ID

3. Grant access (if needed):
   gcloud secrets add-iam-policy-binding SECRET_NAME \\
       --member="serviceAccount:YOUR_SERVICE_ACCOUNT@YOUR_PROJECT.iam.gserviceaccount.com" \\
       --role="roles/secretmanager.secretAccessor" \\
       --project=YOUR_PROJECT_ID

Or use the Secret Manager UI in Google Cloud Console:
https://console.cloud.google.com/security/secret-manager
"""


# Global instance (lazy initialization)
_secret_manager_instance = None


def get_secret_manager() -> SecretManager:
    """Get or create the global SecretManager instance."""
    global _secret_manager_instance
    if _secret_manager_instance is None:
        _secret_manager_instance = SecretManager()
    return _secret_manager_instance
