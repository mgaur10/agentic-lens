"""
X-Ray Librarian — Secure Fetcher tools.

Reads an optional PAT from Secret Manager (`github-pat-token`) or `GITHUB_PAT` /
`GITHUB_TOKEN`. If none is set, uses unauthenticated GitHub API access, which
is sufficient for public repositories (lower rate limits; use a PAT for private
repos or heavier traffic).
"""

from __future__ import annotations

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

SECRET_ID = "github-pat-token"


def _get_project_id() -> str:
    return (
        (os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID") or "")
        .strip()
    )


def _get_github_token() -> Optional[str]:
    """Return PAT from Secret Manager or env, or None for unauthenticated access."""
    if not _SECRET_MANAGER_AVAILABLE:
        return os.getenv("GITHUB_PAT") or os.getenv("GITHUB_TOKEN")
    project_id = _get_project_id()
    if not project_id:
        return os.getenv("GITHUB_PAT") or os.getenv("GITHUB_TOKEN")
    client = SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{SECRET_ID}/versions/latest"
    try:
        response = client.access_secret_version(request={"name": name})
        if response.payload and response.payload.data:
            return response.payload.data.decode("utf-8").strip()
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
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else None
    return repo_url, None


def _collect_paths(repo, path: str, files: list[str], max_files: int = 500) -> None:
    """Recursively collect file paths from the repo."""
    if len(files) >= max_files:
        return
    try:
        for item in repo.get_contents(path):
            item_path = getattr(item, "path", "") or ""
            if getattr(item, "type", None) == "dir":
                _collect_paths(repo, item_path, files, max_files)
            else:
                files.append(item_path)
    except Exception:
        pass


def get_repo_contents(repo_url: str) -> list[str] | str:
    """
    Fetch the list of files in a GitHub repository.

    Uses the github-pat-token from Secret Manager to authenticate with the
    GitHub API. Returns a list of file paths (e.g. main.tf, README.md, src/app.py).

    Args:
        repo_url: GitHub repo URL (e.g. https://github.com/owner/repo) or "owner/repo".

    Returns:
        List of file paths as strings, or an error message string if fetch failed.
    """
    if not _PYGITHUB_AVAILABLE:
        return "Error: PyGithub is not installed. Add PyGithub to requirements."
    token = _get_github_token()
    owner, repo_name = _parse_repo_url(repo_url)
    if not repo_name:
        return f"Error: Could not parse repo from: {repo_url}"
    try:
        # For public repos, GitHub allows unauthenticated access (rate limited). Prefer PAT when available.
        g = github.Github(token) if token else github.Github()
        repo = g.get_repo(f"{owner}/{repo_name}")
        files: list[str] = []
        _collect_paths(repo, "", files)
        return files
    except Exception as e:
        return f"Error fetching repo contents: {e!s}"


def read_file_content(repo_url: str, file_path: str) -> str:
    """
    Fetch the raw text content of a specific file from a GitHub repository.

    Same optional PAT behavior as get_repo_contents.

    Args:
        repo_url: GitHub repo URL (e.g. https://github.com/owner/repo) or "owner/repo".
        file_path: Path to the file in the repo (e.g. main.tf, cloudbuild.yaml, src/app.py).

    Returns:
        Raw text content of the file, or an error message string if fetch failed.
    """
    if not _PYGITHUB_AVAILABLE:
        return "Error: PyGithub is not installed. Add PyGithub to requirements."
    token = _get_github_token()
    owner, repo_name = _parse_repo_url(repo_url)
    if not repo_name:
        return f"Error: Could not parse repo from: {repo_url}"
    file_path = file_path.strip().lstrip("/")
    if not file_path:
        return "Error: file_path must be non-empty."
    try:
        g = github.Github(token) if token else github.Github()
        repo = g.get_repo(f"{owner}/{repo_name}")
        fc = repo.get_contents(file_path)
        if getattr(fc, "content", None):
            import base64
            return base64.b64decode(fc.content).decode("utf-8", errors="replace")
        if getattr(fc, "decoded_content", None) is not None:
            return fc.decoded_content.decode("utf-8", errors="replace")
        return "Error: Could not decode file content."
    except Exception as e:
        return f"Error reading file: {e!s}"
