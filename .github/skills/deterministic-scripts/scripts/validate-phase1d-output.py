#!/usr/bin/env python3
"""Validate and normalize raw Phase 1d output before downstream use."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from phase_output_validation import ValidationError, normalize_phase1d_output, write_json


def _resolve_output_path(workspace_dir: str | None, output_file: str | None) -> Path:
    if output_file:
        return Path(output_file)
    base = Path(workspace_dir) if workspace_dir else Path.cwd()
    base.mkdir(parents=True, exist_ok=True)
    return base / "phase1d-output.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and normalize Phase 1d output")
    parser.add_argument("--raw-output", required=True, help="Raw Phase 1d JSON output")
    parser.add_argument("--workspace-dir", default="", help="Directory for per-run artifacts")
    parser.add_argument("--output-file", default="", help="Path for normalized Phase 1d output")
    args = parser.parse_args()

    try:
        normalized = normalize_phase1d_output(args.raw_output)
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output_path = _resolve_output_path(args.workspace_dir, args.output_file)
    write_json(output_path, normalized)
    print(json.dumps(normalized, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
