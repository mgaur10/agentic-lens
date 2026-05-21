"""
Utility functions for GCP operations and secret management.
"""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

try:
    from google.cloud import secretmanager
    SECRET_MANAGER_AVAILABLE = True
except ImportError:
    SECRET_MANAGER_AVAILABLE = False


def get_secret(secret_id: str, project_id: Optional[str] = None) -> Optional[str]:
    """
    Safely retrieve a secret from GCP Secret Manager.
    
    Args:
        secret_id: The secret ID (name) in Secret Manager (can be with hyphens or underscores)
        project_id: GCP Project ID. If None, reads from GCP_PROJECT_ID env var.
        
    Returns:
        Secret value as string, or None if not found/available
    """
    if not SECRET_MANAGER_AVAILABLE:
        # Fallback to environment variable
        env_key = secret_id.upper().replace("-", "_")
        return os.getenv(env_key)
    
    if not project_id:
        project_id = os.getenv("GCP_PROJECT_ID")
    
    if not project_id:
        # Fallback to environment variable
        env_key = secret_id.upper().replace("-", "_")
        return os.getenv(env_key)
    
    try:
        client = secretmanager.SecretManagerServiceClient()
        # Try the secret_id as-is first
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        try:
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception:
            # If that fails, try with underscores converted to hyphens (Secret Manager uses hyphens)
            secret_id_alt = secret_id.replace("_", "-")
            if secret_id_alt != secret_id:
                name = f"projects/{project_id}/secrets/{secret_id_alt}/versions/latest"
                try:
                    response = client.access_secret_version(request={"name": name})
                    return response.payload.data.decode("UTF-8")
                except Exception:
                    pass
            raise
    except Exception as e:
        # Fallback to environment variable on error
        env_key = secret_id.upper().replace("-", "_")
        fallback_value = os.getenv(env_key)
        if fallback_value:
            return fallback_value
        # Log error silently in production (no print statements)
        return None
