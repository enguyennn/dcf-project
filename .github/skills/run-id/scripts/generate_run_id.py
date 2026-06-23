#!/usr/bin/env python3
"""Generate a short unique run identifier (6 hex characters from UUID4).

Usage:
    python generate_run_id.py

Prints a single 6-character lowercase hex string to stdout.
"""

import uuid


def main() -> None:
    print(uuid.uuid4().hex[:6])


if __name__ == "__main__":
    main()
