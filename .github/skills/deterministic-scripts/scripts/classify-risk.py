#!/usr/bin/env python3
"""Deterministic risk classification based on changed file paths.

Replaces LLM-based risk classification which hallucinated file lists
in 3 consecutive runs despite correct input.

Usage:
    echo '["path/to/file1.cs", "path/to/file2.ts"]' | python classify-risk.py
    python classify-risk.py files.json

Input: JSON array of changed file paths (stdin or file argument).
Output: JSON { "risk_level": "low|medium|high", "signals": [...], "expertise_needed": "..." }
Exit code: 0 always (classification never fails).
"""

import json
import re
import sys
from pathlib import PurePosixPath


# --- Risk pattern rules ---
# Each rule: (glob_pattern, risk_floor, signal_description, expertise)
# Files matching a pattern get AT LEAST the specified risk_floor.

HIGH_PATTERNS = [
    (r"(?i)(^|/)auth/", "New auth flow or auth module change", "Security"),
    (r"(?i)(^|/)crypto/", "Cryptography module change", "Security"),
    (r"(?i)(^|/)secrets?/", "Secrets handling change", "Security"),
    (r"(?i)(^|/)migrations?/", "Database migration", "Database"),
    (r"(?i)(^|/)deploy/", "Deployment configuration change", "Infrastructure"),
    (r"(?i)\.(tf|tfvars|bicep)$", "Infrastructure-as-Code change", "Infrastructure"),
    (r"(?i)(^|/)Dockerfile", "Container image change", "Infrastructure"),
    (r"(?i)(^|/)\.github/workflows/", "CI/CD pipeline change", "Infrastructure"),
    (r"(?i)(^|/)azure-pipelines", "CI/CD pipeline change", "Infrastructure"),
]

MEDIUM_PATTERNS = [
    (r"(?i)(^|/)middleware/", "Middleware change (request pipeline)", "Security"),
    (r"(?i)(^|/)services/", "Service layer change", "Backend"),
    (r"(?i)(^|/)controllers?/", "API controller change", "API Design"),
    (r"(?i)(^|/)api/", "API layer change", "API Design"),
    (r"(?i)(^|/)models?/", "Data model change", "Backend"),
    (r"(?i)appsettings", "Application settings change", "Configuration"),
    (r"(?i)\.(config|env|yaml|yml)$", "Configuration file change", "Configuration"),
    (r"(?i)(^|/)startup\.", "Application startup change", "Backend"),
    (r"(?i)(^|/)program\.", "Application entry point change", "Backend"),
    (r"(?i)(^|/)security", "Security-related file", "Security"),
    (r"(?i)(^|/)validation", "Input validation change", "Security"),
]

# Keywords in file names that bump to at least Medium
SENSITIVE_NAME_KEYWORDS = [
    "password", "token", "secret", "credential", "key", "cert",
    "encrypt", "decrypt", "hash", "jwt", "oauth", "saml", "xss",
    "injection", "sanitiz", "escap",
]

# Patterns that indicate test-only or docs-only (Low risk)
TEST_PATTERNS = [
    r"(?i)(^|/)tests?/",
    r"(?i)\.test\.",
    r"(?i)\.spec\.",
    r"(?i)(^|/)__tests__/",
    r"(?i)Tests?\.(cs|ts|js|py)$",
]

DOCS_PATTERNS = [
    r"(?i)\.(md|txt|rst|adoc)$",
    r"(?i)(^|/)docs?/",
    r"(?i)README",
    r"(?i)CHANGELOG",
    r"(?i)LICENSE",
    r"(?i)CONTRIBUTING",
]


def is_test_file(path: str) -> bool:
    return any(re.search(p, path) for p in TEST_PATTERNS)


def is_docs_file(path: str) -> bool:
    return any(re.search(p, path) for p in DOCS_PATTERNS)


def classify(changed_files: list[str]) -> dict:
    if not changed_files:
        return {
            "risk_level": "low",
            "signals": ["No changed files"],
            "expertise_needed": "",
        }

    signals = []
    max_risk = 0  # 0=low, 1=medium, 2=high
    expertise_set = set()

    # Separate production files from test/docs files
    prod_files = []
    test_files = []
    docs_files = []

    for f in changed_files:
        if is_test_file(f):
            test_files.append(f)
        elif is_docs_file(f):
            docs_files.append(f)
        else:
            prod_files.append(f)

    # If ALL files are tests or docs, it's Low
    if not prod_files:
        categories = []
        if test_files:
            categories.append(f"{len(test_files)} test file(s)")
        if docs_files:
            categories.append(f"{len(docs_files)} doc file(s)")
        return {
            "risk_level": "low",
            "signals": [f"Changes are {' + '.join(categories)} only — no production code modified"],
            "expertise_needed": "",
        }

    # Check each production file against risk patterns
    for f in prod_files:
        # High-risk patterns
        for pattern, description, expertise in HIGH_PATTERNS:
            if re.search(pattern, f):
                max_risk = max(max_risk, 2)
                signals.append(f"🔴 {f}: {description}")
                expertise_set.add(expertise)

        # Medium-risk patterns
        for pattern, description, expertise in MEDIUM_PATTERNS:
            if re.search(pattern, f):
                max_risk = max(max_risk, 1)
                signals.append(f"🟡 {f}: {description}")
                expertise_set.add(expertise)

        # Sensitive name keywords
        fname_lower = PurePosixPath(f).name.lower()
        for kw in SENSITIVE_NAME_KEYWORDS:
            if kw in fname_lower:
                max_risk = max(max_risk, 1)
                signals.append(f"🟡 {f}: File name contains '{kw}'")
                expertise_set.add("Security")

    # If no patterns matched but there are production files, it's still Low
    if not signals:
        signals.append(f"{len(prod_files)} production file(s) changed — no sensitive patterns matched")

    # Add context about test coverage
    if test_files:
        signals.append(f"✅ {len(test_files)} test file(s) included")

    risk_map = {0: "low", 1: "medium", 2: "high"}
    risk_level = risk_map[max_risk]

    expertise = ", ".join(sorted(expertise_set)) if expertise_set else ""

    return {
        "risk_level": risk_level,
        "signals": signals,
        "expertise_needed": expertise,
    }


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            data = f.read()
    else:
        data = sys.stdin.read()

    try:
        changed_files = json.loads(data.strip())
    except json.JSONDecodeError:
        # Try line-delimited format
        changed_files = [line.strip() for line in data.strip().split("\n") if line.strip()]

    if not isinstance(changed_files, list):
        print(json.dumps({"error": "Input must be a JSON array of file paths"}))
        sys.exit(1)

    result = classify(changed_files)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
