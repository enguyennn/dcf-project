#!/usr/bin/env python3
"""Lightweight PR URL parsing shared by deterministic scripts.

This module intentionally has no dependency on pr_platform.py so scripts can
still parse PR URLs when the platform abstraction is unavailable.
"""

from __future__ import annotations

import re

_ADO_PATTERNS = [
    (
        re.compile(
            r"^https://dev\.azure\.com/(?P<org>[^/]+)/(?P<project>[^/]+)/_git/(?P<repo>[^/]+)/pullrequest/(?P<pr_id>\d+)(?:[?#].*)?$",
            re.IGNORECASE,
        ),
        "dev.azure.com",
    ),
    (
        re.compile(
            r"^https://(?P<org>[^.]+)\.visualstudio\.com/(?P<project>[^/]+)/_git/(?P<repo>[^/]+)/pullrequest/(?P<pr_id>\d+)(?:[?#].*)?$",
            re.IGNORECASE,
        ),
        "visualstudio.com",
    ),
    (
        re.compile(
            r"^https://(?P<org>[^.]+)\.visualstudio\.com/DefaultCollection/(?P<project>[^/]+)/_git/(?P<repo>[^/]+)/pullrequest/(?P<pr_id>\d+)(?:[?#].*)?$",
            re.IGNORECASE,
        ),
        "visualstudio.com",
    ),
]

_GITHUB_PATTERN = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<pr_num>\d+)(?:[?#].*)?$",
    re.IGNORECASE,
)


def parse_pr_url(pr_url: str) -> dict[str, str]:
    """Parse an Azure DevOps or GitHub PR URL into a lightweight dict."""
    url = (pr_url or "").strip()

    for pattern, url_type in _ADO_PATTERNS:
        match = pattern.match(url)
        if not match:
            continue

        parts = match.groupdict()
        api_base = (
            f"https://{parts['org']}.visualstudio.com"
            if url_type == "visualstudio.com"
            else f"https://dev.azure.com/{parts['org']}"
        )
        return {
            "platform": "ado",
            "org": parts["org"],
            "project": parts["project"],
            "repo": parts["repo"],
            "pr_id": parts["pr_id"],
            "api_base": api_base,
            "base_url": api_base,
        }

    match = _GITHUB_PATTERN.match(url)
    if match:
        parts = match.groupdict()
        return {
            "platform": "github",
            "owner": parts["owner"],
            "repo": parts["repo"],
            "pr_id": parts["pr_num"],
            "pr_num": parts["pr_num"],
        }

    return {}


def parse_ado_pr_url(pr_url: str) -> dict[str, str]:
    """Parse an Azure DevOps PR URL."""
    parts = parse_pr_url(pr_url)
    return parts if parts.get("platform") == "ado" else {}


def parse_github_pr_url(pr_url: str) -> dict[str, str]:
    """Parse a GitHub PR URL."""
    parts = parse_pr_url(pr_url)
    return parts if parts.get("platform") == "github" else {}
