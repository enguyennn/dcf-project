#!/usr/bin/env python3
"""Parse gkpconfig.yml and validate the Gatekeeper pipeline configuration.

Loads the config file, resolves paths, validates that skills_root exists and
contains guideline skill subdirectories, and outputs a JSON summary.

Usage:
    python parse_config.py --config <path> [--output <path>]
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def _parse_yaml_simple(text: str) -> dict:
    """Minimal YAML parser for gkpconfig.yml (no external dependency).

    Handles the flat key-value and simple nested structure used by gkpconfig.
    Falls back to PyYAML if available.
    """
    if yaml:
        return yaml.safe_load(text) or {}

    result: dict = {}
    current_key = None
    current_list_key = None
    indent_stack: list[tuple[str, dict]] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())

        # Pop indent stack if we've dedented
        while indent_stack and indent <= indent_stack[-1][0]:
            indent_stack.pop()

        if stripped.startswith("- "):
            # List item
            value = stripped[2:].strip().strip("'\"")
            if current_list_key:
                target = indent_stack[-1][1] if indent_stack else result
                if current_list_key not in target:
                    target[current_list_key] = []
                target[current_list_key].append(value)
            continue

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip().strip("'\"")
            val = val.strip().strip("'\"")

            if val:
                # Simple key: value
                target = indent_stack[-1][1] if indent_stack else result
                target[key] = val
                current_list_key = None
            else:
                # Key with nested content
                target = indent_stack[-1][1] if indent_stack else result
                nested: dict = {}
                target[key] = nested
                indent_stack.append((indent, nested))
                current_key = key
                current_list_key = None
                # Check if next values are list items
                current_list_key = None

        # Handle "guidelines:" followed by list items
        if stripped.endswith(":") and not stripped.startswith("- "):
            key = stripped[:-1].strip().strip("'\"")
            current_list_key = key

    return result


def parse_config(config_path: str) -> dict:
    """Parse gkpconfig.yml and return structured config."""
    path = Path(config_path)
    if not path.exists():
        print(f"ERROR: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(encoding="utf-8")

    if yaml:
        config = yaml.safe_load(text) or {}
    else:
        config = _parse_yaml_simple(text)

    return config


def validate_config(config: dict, config_path: str) -> dict:
    """Validate config and return enriched result with validation info."""
    repo_root = config.get("repo_root", ".")
    reviewers = config.get("reviewers", {})
    errors = []
    warnings = []

    if not reviewers:
        errors.append("reviewers section is required in config")

    # Resolve paths relative to config file directory
    config_dir = str(Path(config_path).parent)

    # Check if paths are absolute; if not, resolve relative to config dir
    if repo_root and not os.path.isabs(repo_root):
        repo_root = str(Path(config_dir) / repo_root)

    # Validate repo_root
    if repo_root and not os.path.isdir(repo_root):
        warnings.append(f"repo_root directory not found: {repo_root}")

    # Validate each reviewer entry
    reviewer_names = []
    for name, cfg in reviewers.items():
        if not isinstance(cfg, dict):
            cfg = {}
        reviewer_names.append(name)

        if name == "guidelines_reviewer":
            guidelines_root = cfg.get("guidelines_root")
            if not guidelines_root:
                errors.append(
                    "guidelines_reviewer requires guidelines_root"
                )
            else:
                if not os.path.isabs(guidelines_root):
                    guidelines_root = str(
                        Path(config_dir) / guidelines_root
                    )
                if not os.path.isdir(guidelines_root):
                    errors.append(
                        f"guidelines_root directory not found: "
                        f"{guidelines_root}"
                    )
                else:
                    # Count skills in guidelines_root
                    skills_count = 0
                    for entry in sorted(os.listdir(guidelines_root)):
                        skill_dir = os.path.join(guidelines_root, entry)
                        if os.path.isdir(skill_dir):
                            skill_md = os.path.join(skill_dir, "SKILL.md")
                            if os.path.exists(skill_md):
                                skills_count += 1

    return {
        "config_path": str(Path(config_path).resolve()),
        "repo_root": repo_root,
        "reviewers": reviewer_names,
        "errors": errors,
        "warnings": warnings,
        "valid": len(errors) == 0,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Parse and validate gkpconfig.yml for Gatekeeper pipeline"
    )
    parser.add_argument(
        "--config", required=True,
        help="Path to gkpconfig.yml",
    )
    parser.add_argument("--output", help="Output JSON file path (default: stdout)")
    args = parser.parse_args()

    config = parse_config(args.config)
    result = validate_config(config, args.config)

    output = json.dumps(result, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(output)

    # Summary to stderr
    status = "VALID" if result["valid"] else "INVALID"
    print(
        f"Config: {status}\n"
        f"repo_root: {result['repo_root']}\n"
        f"reviewers: {', '.join(result['reviewers'])}",
        file=sys.stderr,
    )
    for e in result["errors"]:
        print(f"  ERROR: {e}", file=sys.stderr)
    for w in result["warnings"]:
        print(f"  WARNING: {w}", file=sys.stderr)

    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
