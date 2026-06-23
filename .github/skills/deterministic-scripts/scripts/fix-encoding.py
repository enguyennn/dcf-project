#!/usr/bin/env python3
"""Fix Conductor Unicode encoding artifacts on Windows.

Conductor passes strings between agents through cp1252-encoded channels,
garbling multi-byte Unicode characters. This script fixes known patterns.

Usage:
    python fix-encoding.py input.md              # fix file in-place
    python fix-encoding.py input.md output.md    # fix to new file
    cat input.md | python fix-encoding.py        # stdin → stdout

Output: Fixed content. Exit code 0. Reports replacement count to stderr.
"""

import sys

from encoding_utils import load_text_robust

# Garbled → Correct mapping (from FinalDigest Step 7 encoding table)
REPLACEMENTS = {
    "ΓÇö": "—",
    "ΓÇô": "–",
    "Γ£à": "✅",
    "ΓÜá∩╕Å": "⚠️",
    "≡ƒƒí": "🟡",
    "≡ƒƒó": "🟢",
    "≡ƒöÆ": "🔒",
    "≡ƒöº": "🔍",
    "≡ƒöì": "🔬",
    "≡ƒö¿": "🔧",
    "≡ƒº¬": "🧪",
    "≡ƒô¥": "📥",
    "≡ƒöä": "🔄",
    "≡ƒæü∩╕Å": "👁️",
    "≡ƒÆ¡": "💡",
    "≡ƒÆí": "💡",
    "≡ƒñû": "🤖",
    "≡ƒ¢í∩╕Å": "⚡️",
    "ΓåÆ": "→",
    "Γä╣∩╕Å": "ℹ️",
    "ΓÅ│": "⏳",
    "ΓÅ¡∩╕Å": "⏭️",
    "≡ƒöÉ": "🔴",
}


def fix_encoding(content: str) -> tuple[str, int]:
    """Apply all encoding fixes. Returns (fixed_content, replacement_count)."""
    count = 0
    for garbled, correct in REPLACEMENTS.items():
        if garbled in content:
            occurrences = content.count(garbled)
            content = content.replace(garbled, correct)
            count += occurrences
    return content, count


def main():
    if len(sys.argv) > 1:
        input_path = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) > 2 else input_path
        content = load_text_robust(input_path, label="encoding-fix-input", default="") or ""
        fixed, count = fix_encoding(content)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(fixed)
        print(f"{count} replacements made", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        content = sys.stdin.read()
        fixed, count = fix_encoding(content)
        print(fixed)
        print(f"{count} replacements made", file=sys.stderr)


if __name__ == "__main__":
    main()
