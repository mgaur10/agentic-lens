"""
X-Ray Librarian — repo context tool.
Fetches infrastructure/deploy context files from a GitHub repo. Optional PAT from
Secret Manager or env; without a token, uses unauthenticated API access (public repos).
"""

import os
import re
from typing import Optional

try:
    from google.cloud.secretmanager_v1 import SecretManagerServiceClient
    _SECRET_MANAGER_AVAILABLE = True
except ImportError:
    SecretManagerServiceClient = None
    _SECRET_MANAGER_AVAILABLE = False

try:
    import github
    _PYGITHUB_AVAILABLE = True
except ImportError:
    github = None
    _PYGITHUB_AVAILABLE = False

MAX_CONTEXT_BYTES = 50_000  # 50KB limit


def _get_project_id() -> str:
    return (
        (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID") or "")
        .strip()
    )


def _get_github_token() -> Optional[str]:
    if not _SECRET_MANAGER_AVAILABLE:
        return os.getenv("GITHUB_PAT") or os.getenv("GITHUB_TOKEN")
    project_id = _get_project_id()
    if not project_id:
        return os.getenv("GITHUB_PAT") or os.getenv("GITHUB_TOKEN")
    client = SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/github-pat-token/versions/latest"
    try:
        response = client.access_secret_version(request={"name": name})
        if response.payload and response.payload.data:
            return response.payload.data.decode("utf-8")
    except Exception:
        pass
    return os.getenv("GITHUB_PAT") or os.getenv("GITHUB_TOKEN")


def _parse_repo_url(repo_url: str) -> tuple[str, Optional[str]]:
    """Return (owner, repo) or (owner, None) if unparseable."""
    repo_url = repo_url.strip().rstrip("/")
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", repo_url)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", repo_url)
    if m:
        return m.group(1), m.group(2)
    if "/" in repo_url and " " not in repo_url:
        parts = repo_url.split("/", 1)
        return parts[0], parts[1]
    return repo_url, None


def _content_from_file_item(item) -> Optional[str]:
    """Decode content from a PyGithub ContentFile."""
    try:
        if getattr(item, "content", None):
            import base64
            return base64.b64decode(item.content).decode("utf-8", errors="replace")
        if getattr(item, "decoded_content", None) is not None:
            return item.decoded_content.decode("utf-8", errors="replace")
        return None
    except Exception:
        return None


def _get_file_contents(repo, path: str) -> Optional[str]:
    try:
        fc = repo.get_contents(path)
        return _content_from_file_item(fc)
    except Exception:
        return None


def _walk_infra_candidates(repo, directory: str, results: list[tuple[str, str]], total_bytes: list[int]) -> None:
    """Append (path, content) for infra/deploy candidates; total_bytes[0] tracks size."""
    allow_exact = {
        "dockerfile",
        "app.yaml",
        "app.yml",
        "requirements.txt",
        "package.json",
        "docker-compose.yml",
        "docker-compose.yaml",
    }
    try:
        for item in repo.get_contents(directory):
            path = item.path
            if getattr(item, "type", None) == "dir":
                _walk_infra_candidates(repo, path, results, total_bytes)
                continue
            name = getattr(item, "name", "") or ""
            path_lower = path.lower()
            name_lower = name.lower()
            is_candidate = (
                name_lower.endswith(".tf")
                or name_lower in allow_exact
                or path_lower.startswith(".github/workflows/")
                and (name_lower.endswith(".yml") or name_lower.endswith(".yaml"))
            )
            if not is_candidate:
                continue
            content = _content_from_file_item(item)
            if not content:
                continue
            size = len(content.encode("utf-8"))
            if total_bytes[0] + size > MAX_CONTEXT_BYTES:
                remaining = MAX_CONTEXT_BYTES - total_bytes[0]
                content = content.encode("utf-8")[:remaining].decode("utf-8", errors="replace")
                size = len(content.encode("utf-8"))
            results.append((path, content))
            total_bytes[0] += size
            if total_bytes[0] >= MAX_CONTEXT_BYTES:
                return
    except Exception:
        pass


def fetch_repo_context(repo_url: str) -> str:
    """
    Fetch infrastructure/deployment context from a GitHub repository.

    Optional PAT via Secret Manager or env; if absent, PyGithub runs without auth
    (public repositories). Returns file contents up to 50KB total.

    Args:
        repo_url: GitHub repo URL (e.g. https://github.com/owner/repo) or "owner/repo".

    Returns:
        Concatenated file contents as a string, or an error message.
    """
    if not _PYGITHUB_AVAILABLE:
        return "Error: PyGithub is not installed. Add PyGithub to requirements."
    token = _get_github_token()
    owner, repo_name = _parse_repo_url(repo_url)
    if not repo_name:
        return f"Error: Could not parse repo from URL: {repo_url}"
    try:
        g = github.Github(token) if token else github.Github()
        repo = g.get_repo(f"{owner}/{repo_name}")
        results: list[tuple[str, str]] = []
        total_bytes: list[int] = [0]
        # Infrastructure and deploy candidates (limit 50KB total)
        if total_bytes[0] < MAX_CONTEXT_BYTES:
            _walk_infra_candidates(repo, "", results, total_bytes)
        if not results:
            return (
                "No supported infrastructure code found. "
                "Checked Terraform, Dockerfile, app.yaml, requirements.txt, "
                "package.json, docker-compose, and .github/workflows/*.yml."
            )
        return "\n\n".join(f"--- {path} ---\n{content}" for path, content in results)
    except Exception as e:
        return f"Error fetching repo: {e!s}"
