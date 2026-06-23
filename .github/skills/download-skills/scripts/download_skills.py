#!/usr/bin/env python3
"""Download review-derived-skills from azure-core/pandora into .github/skills."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import urllib.error

OWNER = "azure-core"
REPO = "pandora"
BRANCH = "main"
SRC_PATH = "src/gatekeeper-data/crp-guideline-data/guidelines/review-derived-skills"
DEST_SUBDIR = os.path.join(".github", "skills")


def get_gh_token():
    """Get GitHub token via gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def api_get(url, token):
    """Make an authenticated GitHub API GET request."""
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    if token:
        req.add_header("Authorization", f"token {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def download_file(url, dest, token):
    """Download a raw file from GitHub."""
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github.v3.raw")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def download_tree(src_path, dest_dir, token):
    """Recursively download a directory from GitHub."""
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{src_path}?ref={BRANCH}"
    items = api_get(url, token)

    for item in items:
        rel = item["name"]
        if item["type"] == "file":
            file_dest = os.path.join(dest_dir, rel)
            print(f"  {file_dest}")
            download_file(item["url"], file_dest, token)
        elif item["type"] == "dir":
            download_tree(item["path"], os.path.join(dest_dir, rel), token)


def main():
    parser = argparse.ArgumentParser(
        description="Download review-derived-skills into .github/skills"
    )
    parser.add_argument("folder", help="Target root folder (e.g. D:\\Compute-CPlat-Core)")
    args = parser.parse_args()

    dest = os.path.join(args.folder, DEST_SUBDIR)

    # Clear destination
    if os.path.exists(dest):
        print(f"Clearing {dest}")
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)

    token = get_gh_token()
    if not token:
        print("WARNING: No GitHub token found. API rate limits may apply.", file=sys.stderr)

    print(f"Downloading {SRC_PATH} -> {dest}")
    download_tree(SRC_PATH, dest, token)
    print("Done.")


if __name__ == "__main__":
    main()
