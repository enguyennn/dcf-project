#!/usr/bin/env python3
"""Shared PR platform abstraction for PR Orchestrator deterministic scripts."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid
from typing import Any

ADO_RESOURCE = os.environ.get("ADO_RESOURCE_ID", "499b84ac-1321-427f-aa17-267ca6975798")

_PROPAGATE_ENV_KEYS = frozenset({
    "PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP",
    "SYSTEMROOT", "COMSPEC",
    "AZURE_DEVOPS_EXT_PAT", "AZURE_CONFIG_DIR", "AZURE_EXTENSION_DIR",
    "GH_TOKEN", "GITHUB_TOKEN", "GH_CONFIG_DIR",
    "PYTHONPATH", "PYTHONUTF8",
})


@dataclass(frozen=True)
class PrRef:
    """Immutable PR identity parsed from URL."""

    platform: str
    pr_url: str
    org: str | None = None
    project: str | None = None
    repo: str | None = None
    pr_id: str | None = None
    base_url: str | None = None
    owner: str | None = None
    pr_num: str | None = None

    @classmethod
    def from_url(cls, pr_url: str) -> "PrRef":
        """Parse ADO or GitHub PR URL into components."""
        url = (pr_url or "").strip()
        ado_patterns = [
            re.compile(
                r"^https://dev\.azure\.com/(?P<org>[^/]+)/(?P<project>[^/]+)/_git/(?P<repo>[^/]+)/pullrequest/(?P<pr_id>\d+)(?:[?#].*)?$",
                re.IGNORECASE,
            ),
            re.compile(
                r"^https://(?P<org>[^.]+)\.visualstudio\.com/(?P<project>[^/]+)/_git/(?P<repo>[^/]+)/pullrequest/(?P<pr_id>\d+)(?:[?#].*)?$",
                re.IGNORECASE,
            ),
            re.compile(
                r"^https://(?P<org>[^.]+)\.visualstudio\.com/DefaultCollection/(?P<project>[^/]+)/_git/(?P<repo>[^/]+)/pullrequest/(?P<pr_id>\d+)(?:[?#].*)?$",
                re.IGNORECASE,
            ),
        ]
        for pattern in ado_patterns:
            match = pattern.match(url)
            if match:
                parts = match.groupdict()
                base_url = (
                    f"https://{parts['org']}.visualstudio.com"
                    if ".visualstudio.com/" in url.lower()
                    else f"https://dev.azure.com/{parts['org']}"
                )
                return cls(
                    platform="ado",
                    pr_url=url,
                    org=parts["org"],
                    project=parts["project"],
                    repo=parts["repo"],
                    pr_id=parts["pr_id"],
                    base_url=base_url,
                )

        github_match = re.match(
            r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<pr_num>\d+)(?:[?#].*)?$",
            url,
            re.IGNORECASE,
        )
        if github_match:
            parts = github_match.groupdict()
            return cls(
                platform="github",
                pr_url=url,
                owner=parts["owner"],
                repo=parts["repo"],
                pr_num=parts["pr_num"],
            )

        raise ValueError(f"Unsupported PR URL: {pr_url}")

    @property
    def api_base(self) -> str:
        """ADO REST API base URL."""
        if self.platform != "ado" or not all([self.base_url, self.project, self.repo, self.pr_id]):
            raise ValueError("api_base is only available for Azure DevOps PRs")
        return f"{self.base_url}/{self.project}/_apis/git/repositories/{self.repo}/pullRequests/{self.pr_id}"

    @property
    def repo_slug(self) -> str:
        """Human-readable repo identifier."""
        if self.platform == "github":
            return f"{self.owner}/{self.repo}"
        return "/".join(part for part in [self.org, self.project, self.repo] if part)


def run_cli(
    cmd: list[str],
    *,
    check: bool = True,
    timeout: int = 60,
    resource: str | None = None,
) -> subprocess.CompletedProcess:
    """Shared CLI runner with consistent error handling and encoding."""
    full_cmd = list(cmd)
    lowered = [part.lower() for part in full_cmd]
    if resource and len(lowered) >= 2 and lowered[0] == "az" and lowered[1] == "rest" and "--resource" not in lowered:
        full_cmd.extend(["--resource", resource])

    env = {k: v for k, v in os.environ.items() if k in _PROPAGATE_ENV_KEYS}
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out after {timeout}s: {' '.join(full_cmd)}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command not found: {full_cmd[0]}") from exc

    if check and result.returncode != 0:
        stderr = (result.stderr or "").strip()
        message = f"Command failed ({result.returncode}): {' '.join(full_cmd)}"
        if stderr:
            message += f"\n{stderr}"
        print(message, file=os.sys.stderr)
        raise subprocess.CalledProcessError(
            result.returncode,
            full_cmd,
            output=result.stdout,
            stderr=result.stderr,
        )

    return result


class PrBodyOps:
    """Fetch and update PR description."""

    def __init__(self, ref: PrRef):
        self.ref = ref

    def fetch(self) -> str:
        if self.ref.platform == "ado":
            result = run_cli(
                [
                    "az",
                    "repos",
                    "pr",
                    "show",
                    "--id",
                    str(self.ref.pr_id),
                    "--org",
                    str(self.ref.base_url),
                    "--detect",
                    "false",
                    "--query",
                    "description",
                    "-o",
                    "tsv",
                ]
            )
            return result.stdout.rstrip("\r\n")

        result = run_cli(["gh", "pr", "view", self.ref.pr_url, "--json", "body", "-q", ".body"])
        return result.stdout.rstrip("\r\n")

    def update(self, body: str) -> None:
        if self.ref.platform == "ado":
            payload = _write_scratch_file(json.dumps({"description": body}, ensure_ascii=False), ".json", "pr_body")
            try:
                run_cli(
                    [
                        "az",
                        "rest",
                        "--method",
                        "PATCH",
                        "--uri",
                        f"{self.ref.api_base}?api-version=7.1",
                        "--body",
                        f"@{payload}",
                        "--headers",
                        "Content-Type=application/json",
                    ],
                    resource=ADO_RESOURCE,
                )
            finally:
                _cleanup_scratch_file(payload)
            return

        body_file = _write_scratch_file(body, ".md", "pr_body")
        try:
            run_cli(["gh", "pr", "edit", self.ref.pr_url, "--body-file", body_file])
        finally:
            _cleanup_scratch_file(body_file)


class DigestOps:
    """Post/update/find digest comments on a PR."""

    def __init__(self, ref: PrRef):
        self.ref = ref

    def find_existing(self, marker: str) -> dict | None:
        if self.ref.platform == "ado":
            data = _load_json_stdout(
                run_cli(
                    [
                        "az",
                        "rest",
                        "--method",
                        "GET",
                        "--uri",
                        f"{self.ref.api_base}/threads?api-version=7.1",
                    ],
                    resource=ADO_RESOURCE,
                ).stdout
            )
            for thread in data.get("value", []):
                comments = thread.get("comments", [])
                if comments and marker in (comments[0].get("content", "") or ""):
                    return {
                        "thread_id": str(thread.get("id", "")),
                        "comment_id": str(comments[0].get("id", "")),
                        "thread": thread,
                    }
            return None

        comments = _load_json_sequence(
            run_cli(["gh", "api", f"repos/{self.ref.owner}/{self.ref.repo}/issues/{self.ref.pr_num}/comments", "--paginate"]).stdout
        )
        for comment in comments:
            if marker in (comment.get("body", "") or ""):
                return {"comment_id": str(comment.get("id", "")), "comment": comment}
        return None

    def upsert(self, markdown: str, marker: str) -> dict:
        existing = self.find_existing(marker)

        if self.ref.platform == "ado":
            if existing:
                payload = _write_scratch_file(json.dumps({"content": markdown}, ensure_ascii=False), ".json", "digest")
                try:
                    run_cli(
                        [
                            "az",
                            "rest",
                            "--method",
                            "PATCH",
                            "--uri",
                            f"{self.ref.api_base}/threads/{existing['thread_id']}/comments/{existing['comment_id']}?api-version=7.1",
                            "--body",
                            f"@{payload}",
                            "--headers",
                            "Content-Type=application/json",
                        ],
                        resource=ADO_RESOURCE,
                    )
                finally:
                    _cleanup_scratch_file(payload)
                return {
                    "action": "updated",
                    "thread_id": str(existing["thread_id"]),
                    "comment_id": str(existing["comment_id"]),
                }

            payload = _write_scratch_file(
                json.dumps(
                    {
                        "comments": [{"parentCommentId": 0, "content": markdown, "commentType": 1}],
                        "status": 1,
                    },
                    ensure_ascii=False,
                ),
                ".json",
                "digest",
            )
            try:
                created = _load_json_stdout(
                    run_cli(
                        [
                            "az",
                            "rest",
                            "--method",
                            "POST",
                            "--uri",
                            f"{self.ref.api_base}/threads?api-version=7.1",
                            "--body",
                            f"@{payload}",
                            "--headers",
                            "Content-Type=application/json",
                        ],
                        resource=ADO_RESOURCE,
                    ).stdout
                )
            finally:
                _cleanup_scratch_file(payload)
            return {
                "action": "created",
                "thread_id": str(created.get("id", "")),
                "comment_id": str(created.get("comments", [{}])[0].get("id", "")),
            }

        payload = _write_scratch_file(json.dumps({"body": markdown}, ensure_ascii=False), ".json", "digest")
        try:
            if existing:
                run_cli(
                    [
                        "gh",
                        "api",
                        f"repos/{self.ref.owner}/{self.ref.repo}/issues/comments/{existing['comment_id']}",
                        "--method",
                        "PATCH",
                        "--input",
                        payload,
                    ]
                )
                return {"action": "updated", "comment_id": str(existing["comment_id"])}

            created = _load_json_stdout(
                run_cli(
                    [
                        "gh",
                        "api",
                        f"repos/{self.ref.owner}/{self.ref.repo}/issues/{self.ref.pr_num}/comments",
                        "--method",
                        "POST",
                        "--input",
                        payload,
                    ]
                ).stdout
            )
            return {"action": "created", "comment_id": str(created.get("id", ""))}
        finally:
            _cleanup_scratch_file(payload)

    def comment_url(self, thread_id: str, comment_id: str | None = None) -> str:
        if self.ref.platform == "ado":
            return self.ref.pr_url.rstrip("/") + f"?discussionId={thread_id}"
        digest_id = comment_id or thread_id
        return self.ref.pr_url.rstrip("/") + f"#issuecomment-{digest_id}"


class ReviewThreadOps:
    """Post inline findings and list/triage review threads."""

    def __init__(self, ref: PrRef):
        self.ref = ref

    def list_threads(self) -> list[dict]:
        if self.ref.platform == "ado":
            data = _load_json_stdout(
                run_cli(
                    [
                        "az",
                        "rest",
                        "--method",
                        "GET",
                        "--uri",
                        f"{self.ref.api_base}/threads?api-version=7.1",
                    ],
                    resource=ADO_RESOURCE,
                ).stdout
            )
            return data.get("value", [])

        comments = _load_json_sequence(
            run_cli(["gh", "api", f"/repos/{self.ref.owner}/{self.ref.repo}/pulls/{self.ref.pr_num}/comments", "--paginate"]).stdout
        )
        threads = []
        for comment in comments:
            threads.append(
                {
                    "id": comment.get("id"),
                    "status": "",
                    "threadContext": {
                        "filePath": comment.get("path", ""),
                        "rightFileStart": {"line": comment.get("line")},
                    },
                    "comments": [
                        {
                            "id": comment.get("id"),
                            "content": comment.get("body", ""),
                            "author": {
                                "displayName": comment.get("user", {}).get("login", ""),
                                "uniqueName": comment.get("user", {}).get("login", ""),
                            },
                        }
                    ],
                }
            )
        return threads

    def post_inline(self, body: str, file_path: str, line: int, **platform_kwargs) -> dict:
        if self.ref.platform == "ado":
            thread_context: dict[str, Any] = {
                "filePath": file_path if file_path.startswith("/") else f"/{file_path}"
            }
            if line and isinstance(line, int) and line > 0:
                thread_context["rightFileStart"] = {"line": line, "offset": int(platform_kwargs.get("start_offset", 1))}
                thread_context["rightFileEnd"] = {"line": line, "offset": int(platform_kwargs.get("end_offset", 999))}
            payload = {
                "comments": [{"parentCommentId": 0, "content": body, "commentType": int(platform_kwargs.get("comment_type", 1))}],
                "status": int(platform_kwargs.get("status", 1)),
                "threadContext": thread_context,
            }
            payload_file = _write_scratch_file(json.dumps(payload, ensure_ascii=False), ".json", "inline")
            try:
                return _load_json_stdout(
                    run_cli(
                        [
                            "az",
                            "rest",
                            "--method",
                            "POST",
                            "--uri",
                            f"{self.ref.api_base}/threads?api-version=7.1",
                            "--body",
                            f"@{payload_file}",
                            "--headers",
                            "Content-Type=application/json",
                        ],
                        resource=ADO_RESOURCE,
                    ).stdout
                )
            finally:
                _cleanup_scratch_file(payload_file)

        payload_file = _write_scratch_file(
            json.dumps(
                {
                    "body": body,
                    "path": file_path,
                    "line": line,
                    "side": platform_kwargs.get("side", "RIGHT"),
                },
                ensure_ascii=False,
            ),
            ".json",
            "inline",
        )
        try:
            return _load_json_stdout(
                run_cli(
                    [
                        "gh",
                        "api",
                        f"/repos/{self.ref.owner}/{self.ref.repo}/pulls/{self.ref.pr_num}/comments",
                        "--method",
                        "POST",
                        "--input",
                        payload_file,
                    ]
                ).stdout
            )
        finally:
            _cleanup_scratch_file(payload_file)

    def post_pr_level(self, body: str) -> dict:
        if self.ref.platform == "ado":
            payload_file = _write_scratch_file(
                json.dumps(
                    {
                        "comments": [{"parentCommentId": 0, "content": body, "commentType": 1}],
                        "status": 4,
                    },
                    ensure_ascii=False,
                ),
                ".json",
                "pr_level",
            )
            try:
                return _load_json_stdout(
                    run_cli(
                        [
                            "az",
                            "rest",
                            "--method",
                            "POST",
                            "--uri",
                            f"{self.ref.api_base}/threads?api-version=7.1",
                            "--body",
                            f"@{payload_file}",
                            "--headers",
                            "Content-Type=application/json",
                        ],
                        resource=ADO_RESOURCE,
                    ).stdout
                )
            finally:
                _cleanup_scratch_file(payload_file)

        result = run_cli(["gh", "pr", "comment", self.ref.pr_url, "--body", body])
        return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}


def _scratch_dir() -> Path:
    return Path(__file__).resolve().parent


def _write_scratch_file(content: str, suffix: str, prefix: str) -> str:
    path = _scratch_dir() / f".{prefix}_{os.getpid()}_{uuid.uuid4().hex}{suffix}"
    path.write_text(content, encoding="utf-8")
    return str(path)


def _cleanup_scratch_file(path: str | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _load_json_stdout(text: str) -> dict:
    stripped = (text or "").strip()
    if not stripped:
        return {}
    return json.loads(stripped)


def _load_json_sequence(text: str) -> list[dict]:
    stripped = (text or "").strip()
    if not stripped:
        return []
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        return []
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        items: list[dict] = []
        idx = 0
        while idx < len(stripped):
            while idx < len(stripped) and stripped[idx].isspace():
                idx += 1
            if idx >= len(stripped):
                break
            parsed, end = decoder.raw_decode(stripped, idx)
            if isinstance(parsed, list):
                items.extend(item for item in parsed if isinstance(item, dict))
            elif isinstance(parsed, dict):
                items.append(parsed)
            idx = end
        return items
