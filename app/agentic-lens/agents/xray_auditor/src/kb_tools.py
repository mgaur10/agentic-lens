"""
Self-Learning IAM Knowledge Base — Firestore collection `iam_knowledge_base`.

Dependency: google-cloud-firestore.

- lookup_resource_iam(resource_type): Query the collection; return cached permissions if found.
- learn_resource_iam(resource_type, permissions, role): Save a NEW validated mapping to Firestore.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

try:
    from google.cloud import firestore
    _FIRESTORE_AVAILABLE = True
except ImportError:
    firestore = None
    _FIRESTORE_AVAILABLE = False

COLLECTION_ID = "iam_knowledge_base"
# Firestore database ID (create in console if missing). Override with XRAY_KB_DATABASE env.
FIRESTORE_DATABASE_ID = os.environ.get("XRAY_KB_DATABASE", "xray-db")


def _get_client() -> "firestore.Client | None":
    if not _FIRESTORE_AVAILABLE:
        return None
    try:
        project = (os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "").strip()
        return firestore.Client(project=project, database=FIRESTORE_DATABASE_ID)
    except Exception:
        return None


def _doc_id(resource_type: str) -> str:
    """Sanitize resource_type for use as a Firestore document ID."""
    if not resource_type or not isinstance(resource_type, str):
        return ""
    return resource_type.strip().replace("/", "_")[:1500]


def lookup_resource_iam(resource_type: str) -> dict[str, Any] | None:
    """
    Look up cached IAM permissions for a Terraform resource type.

    Args:
        resource_type: Terraform resource name (e.g. google_sql_database_instance, google_redis_instance).

    Returns:
        Stored JSON with keys such as permissions, recommended_role, source_url, updated_at,
        or None if not found or Firestore unavailable.
    """
    client = _get_client()
    if client is None:
        return None
    doc_id = _doc_id(resource_type)
    if not doc_id:
        return None
    try:
        doc_ref = client.collection(COLLECTION_ID).document(doc_id)
        doc = doc_ref.get()
        if doc and doc.exists:
            data = doc.to_dict()
            if data:
                return dict(data)
        return None
    except Exception:
        return None


def learn_resource_iam(
    resource_type: str,
    permissions: list[str],
    role: str,
    source_url: str = "",
) -> str:
    """
    Save a validated IAM mapping to the knowledge base.

    Call this after finding the answer in official documentation so future
    requests can use the cache (Lookup -> Search -> Learn).

    Args:
        resource_type: Terraform resource name (e.g. google_sql_database_instance).
        permissions: List of IAM permissions required (e.g. ["redis.instances.get"]).
        role: Recommended role (e.g. roles/redis.viewer).
        source_url: Optional. URL of the documentation source.

    Returns:
        Success message or error description.
    """
    client = _get_client()
    if client is None:
        return "Knowledge base unavailable (google-cloud-firestore not configured or client failed)."
    doc_id = _doc_id(resource_type)
    if not doc_id:
        return "Invalid resource_type."
    try:
        doc_ref = client.collection(COLLECTION_ID).document(doc_id)
        doc_ref.set({
            "resource_type": resource_type,
            "permissions": list(permissions) if permissions else [],
            "role": role or "",
            "recommended_role": role or "",  # backward compatibility for lookup
            "source_url": source_url or "",
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        })
        return f"Saved IAM findings for {resource_type} to knowledge base."
    except Exception as e:
        err_str = str(e).strip()
        # Firestore/Datastore not enabled for project — return friendly skip message
        if "404" in err_str or "does not exist" in err_str.lower() or "database" in err_str.lower():
            return (
                "Knowledge base save skipped (Firestore not enabled for this project). "
                "IAM findings were still computed; to enable caching, add a Firestore database in the project."
            )
        return f"Failed to save to knowledge base: {e}"
