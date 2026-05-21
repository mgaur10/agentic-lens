"""
X-Ray Specialist — domain-restricted search for IAM inference.

Ensures the agent only uses information from:
- cloud.google.com (Official GCP Documentation)
- github.com (Source Code & Official Actions)
- registry.terraform.io (Official Provider Docs)

Use get_restricted_search_query() or restricted_search() when wiring any search tool.
"""

from typing import Callable

# Suffix to append to every search query so results are limited to authorized domains.
SITE_RESTRICTION = " (site:cloud.google.com OR site:github.com OR site:registry.terraform.io)"


def get_restricted_search_query(query: str) -> str:
    """
    Force domain restriction on a search query.
    Use this when constructing queries for Google Search or any search tool.
    """
    q = (query or "").strip()
    if not q:
        return q
    # Avoid appending the restriction twice if the agent already added it.
    if "site:cloud.google.com" in q or "site:github.com" in q or "site:registry.terraform.io" in q:
        return q
    return f"{q}{SITE_RESTRICTION}"


def restricted_search(query: str, search_function: Callable[[str], str] | None = None) -> str:
    """
    Run a search with domain restriction applied to the query.
    If search_function is provided, calls it with the restricted query and returns the result.
    Otherwise returns the restricted query string (for use by the agent or another tool).
    """
    safe_query = get_restricted_search_query(query)
    if search_function is not None:
        return search_function(safe_query)
    return safe_query
