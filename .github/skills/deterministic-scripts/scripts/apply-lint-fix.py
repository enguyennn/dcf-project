#!/usr/bin/env python3
"""Apply scoped lint auto-fixes for PR-changed files only."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


os.environ.setdefault("PYTHONIOENCODING", "utf-8")

DOTNET_EXTENSIONS = {".cs", ".csproj"}
NODE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}
PYTHON_EXTENSIONS = {".py"}
FORMATTER_ORDER = ("dotnet", "node", "python")


def normalize_path(path: str) -> str:
    text = str(path).strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def emit_result(status: str, files_fixed: list[str], illegal_files: list[str], commit_sha: str = "") -> None:
    print(json.dumps({
        "status": status,
        "files_fixed": files_fixed,
        "illegal_files": illegal_files,
        "commit_sha": commit_sha,
    }, ensure_ascii=False))


def run_command(cmd: list[str], *, timeout: int = 300, cwd: str | None = None) -> subprocess.CompletedProcess:
    kwargs = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "encoding": "utf-8",
        "errors": "replace",
        "shell": False,
        "cwd": cwd,
    }
    # On Windows, npm/npx are batch files that require cmd.exe to invoke.
    # Use ['cmd.exe', '/c', ...] with shell=False to avoid shell metacharacter injection
    # that shell=True + list2cmdline would allow (e.g. paths with & | > ^ characters).
    if os.name == "nt" and cmd and cmd[0].lower() in {"npm", "npx"}:
        return subprocess.run(["cmd.exe", "/c", subprocess.list2cmdline(cmd)], **kwargs)
    try:
        return subprocess.run(cmd, **kwargs)
    except FileNotFoundError:
        if os.name != "nt" or not cmd:
            raise
        fallback_args = ["cmd.exe", "/c", subprocess.list2cmdline(cmd)]
        return subprocess.run(fallback_args, **kwargs)


def load_allowlist(path: str) -> list[str]:
    json_path = Path(path)
    if not json_path.exists():
        raise FileNotFoundError(f"Changed-files JSON not found: {json_path}")
    with json_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list) or any(not isinstance(item, str) for item in payload):
        raise ValueError("Changed-files JSON must contain an array of relative file paths")
    return dedupe_preserve_order(normalize_path(item) for item in payload)


def filter_files(files: list[str], extensions: set[str]) -> list[str]:
    return [item for item in files if Path(item).suffix.lower() in extensions]


def detect_project_types(allowlist: list[str], requested: str) -> list[str]:
    if requested != "auto":
        return [requested]

    detected = []
    if filter_files(allowlist, DOTNET_EXTENSIONS):
        detected.append("dotnet")
    if filter_files(allowlist, NODE_EXTENSIONS):
        detected.append("node")
    if filter_files(allowlist, PYTHON_EXTENSIONS):
        detected.append("python")
    return detected


def git_repo_root() -> Path:
    result = run_command(["git", "rev-parse", "--show-toplevel"], timeout=30)
    if result.returncode == 0:
        root = result.stdout.strip()
        if root:
            return Path(root)
    return Path.cwd()


def find_solution_file(explicit_solution: str | None) -> str:
    if explicit_solution:
        candidate = Path(explicit_solution)
        if candidate.exists():
            return str(candidate)
        raise FileNotFoundError(f"Solution file not found: {candidate}")

    cwd = Path.cwd()
    repo_root = git_repo_root()
    candidates = []
    for search_root in dedupe_preserve_order([str(cwd), str(repo_root)]):
        root = Path(search_root)
        candidates.extend(sorted(root.glob("*.sln")))
    if not candidates:
        for search_root in dedupe_preserve_order([str(cwd), str(repo_root)]):
            root = Path(search_root)
            candidates.extend(sorted(root.glob("**/*.sln")))
    if not candidates:
        raise FileNotFoundError("No .sln file found for dotnet auto-fix")
    return str(candidates[0])


def format_dotnet(files: list[str], solution: str) -> subprocess.CompletedProcess:
    return run_command(["dotnet", "format", solution, "--include", *files], timeout=600)


def format_node(files: list[str]) -> subprocess.CompletedProcess:
    result = run_command(["npx", "eslint", "--fix", *files], timeout=600)
    if result.returncode == 0:
        return result
    if "could not determine executable to run" in (result.stderr or "").lower() or "command not found" in (result.stderr or "").lower():
        return run_command(["npm", "run", "lint", "--", "--fix", *files], timeout=600)
    return result


def format_python(files: list[str]) -> subprocess.CompletedProcess:
    return run_command(["ruff", "check", "--fix", *files], timeout=600)


def run_formatters(project_types: list[str], allowlist: list[str], solution: str | None) -> tuple[bool, list[str], str]:
    targeted_files: list[str] = []

    for project_type in project_types:
        if project_type == "dotnet":
            files = filter_files(allowlist, DOTNET_EXTENSIONS)
            if not files:
                continue
            if not solution:
                return False, targeted_files, "No .sln file found for dotnet auto-fix"
            print(f"Running dotnet format for {len(files)} file(s)", file=sys.stderr)
            result = format_dotnet(files, solution)
        elif project_type == "node":
            files = filter_files(allowlist, NODE_EXTENSIONS)
            if not files:
                continue
            print(f"Running eslint --fix for {len(files)} file(s)", file=sys.stderr)
            result = format_node(files)
        elif project_type == "python":
            files = filter_files(allowlist, PYTHON_EXTENSIONS)
            if not files:
                continue
            print(f"Running ruff --fix for {len(files)} file(s)", file=sys.stderr)
            result = format_python(files)
        else:
            return False, targeted_files, f"Unsupported project type: {project_type}"

        if not files:
            continue
        targeted_files.extend(files)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or f"Formatter exited with {result.returncode}").strip()
            return False, dedupe_preserve_order(targeted_files), detail

    return True, dedupe_preserve_order(targeted_files), ""


def parse_git_status() -> dict[str, str]:
    result = run_command(["git", "status", "--porcelain"], timeout=30)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or f"git status failed with {result.returncode}").strip()
        raise RuntimeError(detail)

    statuses: dict[str, str] = {}
    for raw_line in result.stdout.splitlines():
        if not raw_line:
            continue
        status = raw_line[:2]
        if status == "!!":
            continue
        path_text = raw_line[3:] if len(raw_line) > 3 else ""
        if not path_text:
            continue
        if " -> " in path_text:
            old_path, new_path = path_text.split(" -> ", 1)
            statuses[normalize_path(old_path)] = status
            statuses[normalize_path(new_path)] = status
            continue
        statuses[normalize_path(path_text)] = status
    return statuses


_STAGED_OR_MODIFIED = set("MADRCU")


def modified_file_set(statuses: dict[str, str]) -> set[str]:
    return {path for path, st in statuses.items() if any(ch in _STAGED_OR_MODIFIED for ch in st)}


def is_tracked_file(path: str) -> bool:
    result = run_command(["git", "ls-files", "--error-unmatch", "--", path], timeout=30)
    return result.returncode == 0


def revert_files(files: list[str]) -> None:
    if not files:
        return
    print(f"Reverting {len(files)} out-of-scope file(s)", file=sys.stderr)
    tracked = [path for path in files if is_tracked_file(path)]
    untracked = [path for path in files if path not in tracked]
    if tracked:
        run_command(["git", "checkout", "HEAD", "--", *tracked], timeout=120)
    for file_path in untracked:
        candidate = Path(file_path)
        if candidate.is_dir():
            for child in sorted(candidate.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    try:
                        child.rmdir()
                    except OSError as exc:
                        import warnings
                        warnings.warn(f"Could not remove directory {child}: {exc}")
            candidate.rmdir()
        elif candidate.exists():
            candidate.unlink(missing_ok=True)


def build_commit_message(files_fixed: list[str]) -> str:
    lines = [
        "style: auto-fix lint violations in PR-scoped files",
        "",
        f"Fixed {len(files_fixed)} file(s):",
        *[f"- {path}" for path in files_fixed],
    ]
    return "\n".join(lines)


def commit_files(files_fixed: list[str]) -> str:
    add_result = run_command(["git", "add", "--", *files_fixed], timeout=120)
    if add_result.returncode != 0:
        detail = (add_result.stderr or add_result.stdout or "git add failed").strip()
        raise RuntimeError(detail)

    commit_message = build_commit_message(files_fixed)
    commit_result = run_command(["git", "commit", "-m", commit_message], timeout=120)
    if commit_result.returncode != 0:
        detail = (commit_result.stderr or commit_result.stdout or "git commit failed").strip()
        raise RuntimeError(detail)

    sha_result = run_command(["git", "rev-parse", "HEAD"], timeout=30)
    if sha_result.returncode != 0:
        detail = (sha_result.stderr or sha_result.stdout or "git rev-parse HEAD failed").strip()
        raise RuntimeError(detail)
    return sha_result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply scoped lint auto-fixes")
    parser.add_argument("--changed-files", required=True, help="Path to JSON file containing changed file paths")
    parser.add_argument("--project-type", choices=["dotnet", "node", "python", "auto"], default="auto")
    parser.add_argument("--solution", help="Path to solution file for dotnet repos")
    parser.add_argument("--dry-run", action="store_true", help="Run formatter and stage preview without committing")
    args = parser.parse_args(argv)

    try:
        allowlist = load_allowlist(args.changed_files)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        emit_result("formatter_failed", [], [], "")
        return 2

    if not allowlist:
        print("Allowlist is empty; nothing to fix", file=sys.stderr)
        emit_result("clean", [], [], "")
        return 0

    project_types = detect_project_types(allowlist, args.project_type)
    if not project_types:
        print("No formatter-relevant files found in allowlist", file=sys.stderr)
        emit_result("clean", [], [], "")
        return 0

    solution = None
    if "dotnet" in project_types:
        try:
            solution = find_solution_file(args.solution)
        except (FileNotFoundError, OSError) as exc:
            print(str(exc), file=sys.stderr)
            emit_result("formatter_failed", [], [], "")
            return 2

    try:
        pre_status = parse_git_status()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        emit_result("formatter_failed", [], [], "")
        return 2

    succeeded, targeted_files, formatter_error = run_formatters(project_types, allowlist, solution)
    if not targeted_files:
        print("No formatter-relevant files found after filtering", file=sys.stderr)
        emit_result("clean", [], [], "")
        return 0
    if not succeeded:
        print(formatter_error, file=sys.stderr)
        emit_result("formatter_failed", [], [], "")
        return 2

    try:
        post_status = parse_git_status()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        emit_result("formatter_failed", [], [], "")
        return 2

    allowlist_set = set(allowlist)
    post_modified = modified_file_set(post_status)
    illegal_files = sorted(post_modified - allowlist_set)
    if illegal_files:
        revert_files(illegal_files)
        print(
            "Scope violation detected. Reverted out-of-scope files: " + ", ".join(illegal_files),
            file=sys.stderr,
        )
        emit_result("scope_violation", [], illegal_files, "")
        return 1

    pre_modified = modified_file_set(pre_status)
    targeted_set = set(targeted_files)
    files_fixed = sorted(
        path for path in (post_modified & targeted_set)
        if path not in pre_modified or post_status.get(path) != pre_status.get(path)
    )
    if not files_fixed:
        print("Formatter produced no changes", file=sys.stderr)
        emit_result("clean", [], [], "")
        return 0

    if args.dry_run:
        print("Dry run: would stage files: " + ", ".join(files_fixed), file=sys.stderr)
        emit_result("fixed", files_fixed, [], "")
        return 0

    try:
        commit_sha = commit_files(files_fixed)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        emit_result("formatter_failed", files_fixed, [], "")
        return 2

    print(f"Committed scoped lint fixes: {commit_sha}", file=sys.stderr)
    emit_result("fixed", files_fixed, [], commit_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
