"""
X-Ray Librarian tools — IAM knowledge base lookup.
Provides lookup_resource_iam for use by the X-Ray Specialist/Auditor.
"""
import os

def lookup_resource_iam(resource_name: str, project_id: str = "") -> str:
    """
    Look up IAM policy for a GCP resource.

    Args:
        resource_name: Resource to look up (e.g., 'projects/my-project' or just 'my-project').
        project_id: Optional project override.

    Returns:
        str: IAM bindings or error message.
    """
    project = project_id or os.environ.get("GCP_PROJECT_ID", "")
    resource = resource_name if "/" in resource_name else f"projects/{project}"
    try:
        from google.cloud import resourcemanager_v3
        client = resourcemanager_v3.ProjectsClient()
        policy = client.get_iam_policy(resource=resource)
        bindings = [
            f"  {b.role}: {', '.join(b.members)}"
            for b in policy.bindings
        ]
        return f"IAM Policy for {resource}:\n" + "\n".join(bindings) if bindings else "No bindings found"
    except Exception as e:
        return f"IAM lookup failed for {resource}: {e}"


def learn_resource_iam(resource_name: str, iam_note: str, project_id: str = "") -> str:
    """
    Record a note about a resource's IAM configuration.

    Args:
        resource_name: The GCP resource name.
        iam_note: A note about the IAM configuration.
        project_id: Optional project override.

    Returns:
        str: Confirmation message.
    """
    # In QA, this is a no-op (would normally update a knowledge base)
    return f"[Librarian] Recorded IAM note for {resource_name}: {iam_note[:100]}"
