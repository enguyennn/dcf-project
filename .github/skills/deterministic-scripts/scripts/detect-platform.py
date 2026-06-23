#!/usr/bin/env python3
"""Detect CI platform from git remote URL.

Usage:
    echo 'https://dev.azure.com/org/project/_git/repo' | python detect-platform.py
    python detect-platform.py 'git@github.com:owner/repo.git'
    python detect-platform.py  # auto-detects from git config

Output: JSON { "platform": "ado|github", "org": "...", "project": "...", "repo": "..." }
"""

import json
import re
import subprocess
import sys


def get_remote_url() -> str:
    """Get git remote URL from argument, stdin, or git config."""
    if len(sys.argv) > 1:
        return sys.argv[1].strip()

    if not sys.stdin.isatty():
        return sys.stdin.read().strip()

    # Auto-detect from git config
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return ""


# ADO patterns
ADO_HTTPS = re.compile(
    r"https?://(?:[^@]+@)?dev\.azure\.com/(?P<org>[^/]+)/(?P<project>[^/]+)/_git/(?P<repo>[^/\s]+)"
)
ADO_SSH = re.compile(
    r"git@ssh\.dev\.azure\.com:v3/(?P<org>[^/]+)/(?P<project>[^/]+)/(?P<repo>[^/\s]+)"
)
ADO_VISUALSTUDIO = re.compile(
    r"https?://(?P<org>[^.]+)\.visualstudio\.com/(?:DefaultCollection/)?(?P<project>[^/]+)/_git/(?P<repo>[^/\s]+)"
)

# GitHub patterns
GITHUB_HTTPS = re.compile(
    r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/\s]+?)(?:\.git)?$"
)
GITHUB_SSH = re.compile(
    r"git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/\s]+?)(?:\.git)?$"
)


def detect(url: str) -> dict:
    if not url:
        return {"platform": "unknown", "error": "No remote URL provided"}

    # ADO HTTPS
    m = ADO_HTTPS.search(url)
    if m:
        return {
            "platform": "ado",
            "org": m.group("org"),
            "project": m.group("project"),
            "repo": m.group("repo"),
        }

    # ADO SSH
    m = ADO_SSH.search(url)
    if m:
        return {
            "platform": "ado",
            "org": m.group("org"),
            "project": m.group("project"),
            "repo": m.group("repo"),
        }

    # ADO *.visualstudio.com (legacy)
    m = ADO_VISUALSTUDIO.search(url)
    if m:
        return {
            "platform": "ado",
            "org": m.group("org"),
            "project": m.group("project"),
            "repo": m.group("repo"),
        }

    # GitHub HTTPS
    m = GITHUB_HTTPS.search(url)
    if m:
        return {
            "platform": "github",
            "owner": m.group("owner"),
            "repo": m.group("repo"),
        }

    # GitHub SSH
    m = GITHUB_SSH.search(url)
    if m:
        return {
            "platform": "github",
            "owner": m.group("owner"),
            "repo": m.group("repo"),
        }

    return {"platform": "unknown", "error": f"Unrecognized URL format: {url}"}


def main():
    url = get_remote_url()
    result = detect(url)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
