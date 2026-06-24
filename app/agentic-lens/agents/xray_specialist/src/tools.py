"""X-Ray Specialist tools — IAM lookup and verification."""
import os


def lookup_resource_iam(resource_name: str, project_id: str = "") -> str:
    """
    Look up IAM policy for a GCP resource.

    Args:
        resource_name: The resource to look up (e.g., 'projects/my-project').
        project_id: Optional project ID override.

    Returns:
        str: IAM policy information or error message.
    """
    project = project_id or os.environ.get("GCP_PROJECT_ID", "")
    try:
        from google.cloud import resourcemanager_v3
        client = resourcemanager_v3.ProjectsClient()
        # Get IAM policy
        from google.iam.v1 import iam_policy_pb2
        resource = resource_name if resource_name.startswith("projects/") else f"projects/{project}"
        policy = client.get_iam_policy(resource=resource)
        bindings = []
        for binding in policy.bindings:
            members = ", ".join(binding.members)
            bindings.append(f"  {binding.role}: {members}")
        if bindings:
            return f"IAM Policy for {resource}:\n" + "\n".join(bindings)
        return f"No IAM bindings found for {resource}"
    except Exception as e:
        return f"IAM lookup error for {resource_name}: {e}"
