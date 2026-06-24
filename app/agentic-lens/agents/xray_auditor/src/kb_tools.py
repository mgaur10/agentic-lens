"""X-Ray Auditor KB tools — read-only IAM knowledge base lookup."""

def lookup_resource_iam(resource_name: str, project_id: str = "") -> str:
    """
    Look up IAM policy for a resource (read-only).

    Args:
        resource_name: Resource to check.
        project_id: Optional project override.

    Returns:
        str: IAM policy or error.
    """
    import os
    project = project_id or os.environ.get("GCP_PROJECT_ID", "")
    try:
        from google.cloud import resourcemanager_v3
        client = resourcemanager_v3.ProjectsClient()
        resource = resource_name if resource_name.startswith("projects/") else f"projects/{project}"
        policy = client.get_iam_policy(resource=resource)
        bindings = []
        for binding in policy.bindings:
            members = ", ".join(binding.members)
            bindings.append(f"  {binding.role}: {members}")
        return f"IAM Policy for {resource}:\n" + "\n".join(bindings) if bindings else "No bindings"
    except Exception as e:
        return f"Lookup error: {e}"
