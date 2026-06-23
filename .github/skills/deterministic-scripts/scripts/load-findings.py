#!/usr/bin/env python3
"""Load and validate a JSON findings file, printing its contents to stdout."""
import json
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: load-findings.py <findings_json_path>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = f.read()
        json.loads(data)  # validate
        print(data)
    except FileNotFoundError:
        print(f"Findings file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
