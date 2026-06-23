#!/usr/bin/env python3
"""Shared encoding and HTML sanitization helpers for deterministic scripts."""

from __future__ import annotations

import ast
import html
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_ENCODING_CHAIN = ["utf-8", "utf-8-sig", "utf-16-le", "utf-16-be", "cp1252"]
_BOMS: list[tuple[bytes, str]] = [
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
]


def _label(path: str | os.PathLike[str], label: str | None = None) -> str:
    return label or Path(path).name or "json"


def sanitize_llm_json(text: str) -> str:
    """Normalize common LLM-emitted JSON defects before parsing."""
    if not isinstance(text, str):
        return text

    sanitized = text.lstrip("\ufeff").strip()
    sanitized = re.sub(r"^```(?:json)?\s*", "", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\s*```$", "", sanitized)
    sanitized = sanitized.replace("\\'", "'")
    sanitized = re.sub(r",\s*([}\]])", r"\1", sanitized)
    return sanitized


def clean_html(text: Any, *, max_length: int | None = None) -> str:
    """Strip HTML, badges, entities, and repeated whitespace from thread text."""
    if text is None:
        return ""

    cleaned = str(text).replace("\ufeff", "")
    cleaned = re.sub(
        r"^\s*<span\b[^>]*>\s*PR\s*Assistant\s*</span>\s*",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"^\s*<small\b[^>]*class=\"[^\"]*flex-row[^\"]*\"[^>]*>.*?</small>\s*",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"^\s*<small\b[^>]*class=\"secondary-text\"[^>]*>.*?</small>\s*",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(
        r"\s*<small\b[^>]*class=\"secondary-text\"[^>]*>.*?</small>\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )

    cleaned = re.sub(r"```suggestion.*?```", " ", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"Here is the suggested code:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</p\s*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<li\b[^>]*>", "- ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</li\s*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if max_length and len(cleaned) > max_length:
        return cleaned[: max_length - 3].rstrip() + "..."
    return cleaned


def validate_encoding(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Inspect a file's leading bytes and return best-effort encoding metadata."""
    file_path = Path(path)
    info: dict[str, Any] = {
        "path": str(file_path),
        "exists": file_path.exists(),
        "readable": False,
        "encoding": "unknown",
        "bom": False,
        "size": 0,
        "warnings": [],
    }

    if not file_path.exists():
        info["warnings"].append("file_not_found")
        return info

    try:
        info["size"] = file_path.stat().st_size
        with file_path.open("rb") as handle:
            sample = handle.read(4096)
    except OSError as exc:
        info["warnings"].append(f"read_error: {exc}")
        return info

    if not sample:
        info["readable"] = True
        info["encoding"] = "utf-8"
        return info

    for bom, encoding in _BOMS:
        if sample.startswith(bom):
            info["readable"] = True
            info["encoding"] = encoding
            info["bom"] = True
            return info

    even_nulls = sample[1::2].count(0)
    odd_nulls = sample[0::2].count(0)
    if even_nulls > max(1, odd_nulls * 2) and even_nulls > len(sample) // 8:
        info["readable"] = True
        info["encoding"] = "utf-16-le"
        info["warnings"].append("utf16_without_bom")
        return info
    if odd_nulls > max(1, even_nulls * 2) and odd_nulls > len(sample) // 8:
        info["readable"] = True
        info["encoding"] = "utf-16-be"
        info["warnings"].append("utf16_without_bom")
        return info

    try:
        sample.decode("utf-8")
        info["readable"] = True
        info["encoding"] = "utf-8"
        return info
    except UnicodeDecodeError as utf8_err:
        # If the decode error is in the last 3 bytes AND the sample was truncated
        # (file larger than sample), the read likely split a multi-byte UTF-8
        # character at the boundary. Retry without trailing bytes.
        if utf8_err.start >= len(sample) - 3 and info["size"] > len(sample):
            try:
                sample[: utf8_err.start].decode("utf-8")
                info["readable"] = True
                info["encoding"] = "utf-8"
                info["warnings"].append("truncated_multibyte_at_boundary")
                return info
            except UnicodeDecodeError:
                pass

    try:
        sample.decode("cp1252")
        info["readable"] = True
        info["encoding"] = "cp1252"
        info["warnings"].append("non_utf8_bytes_detected")
    except UnicodeDecodeError as exc:
        info["warnings"].append(f"unknown_encoding: {exc}")
    return info


def _encoding_candidates(info: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    detected = info.get("encoding")
    if detected in _ENCODING_CHAIN:
        candidates.append(detected)
    for encoding in _ENCODING_CHAIN:
        if encoding not in candidates:
            candidates.append(encoding)
    return candidates


def _parse_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        sanitized = sanitize_llm_json(text)
        if sanitized != text:
            try:
                return json.loads(sanitized)
            except json.JSONDecodeError:
                text = sanitized
        parsed = ast.literal_eval(text)
        if isinstance(parsed, (dict, list)):
            return parsed
        raise


def load_text_robust(
    path: str | os.PathLike[str],
    *,
    label: str | None = None,
    default: str | None = None,
) -> str | None:
    """Load text using the shared encoding fallback chain."""
    file_path = Path(path)
    name = _label(file_path, label)
    if not file_path.exists():
        print(f"WARNING: {name} file not found: {file_path}", file=sys.stderr)
        return default

    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        print(f"WARNING: Could not read {name} from {file_path}: {exc}", file=sys.stderr)
        return default

    info = validate_encoding(file_path)
    parse_errors: list[str] = []
    for encoding in _encoding_candidates(info):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError as exc:
            parse_errors.append(f"{encoding}: decode error ({exc})")
            continue
        # Normalize line endings — bytes-level decode preserves \r\n which
        # causes double-newline corruption when later written in text mode
        # on Windows (\r\n → \r\r\n on disk → \n\n on next read).
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Normalize to UTF-8 — replace any characters not encodable in UTF-8
        text = text.encode("utf-8", "replace").decode("utf-8")
        if encoding != "utf-8" or info.get("warnings"):
            warning_suffix = f" warnings={info.get('warnings')}" if info.get("warnings") else ""
            print(
                f"INFO: Loaded {name} from {file_path} using {encoding}{warning_suffix}",
                file=sys.stderr,
            )
        return text

    print(
        f"WARNING: Could not decode {name} from {file_path}: {'; '.join(parse_errors[-3:])}",
        file=sys.stderr,
    )
    return default


def load_json_robust(
    path: str | os.PathLike[str],
    *,
    label: str | None = None,
    default: Any = None,
) -> Any:
    """Load JSON with robust encoding and sanitization fallbacks."""
    file_path = Path(path)
    name = _label(file_path, label)
    if not file_path.exists():
        print(f"WARNING: {name} file not found: {file_path}", file=sys.stderr)
        return default

    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        print(f"WARNING: Could not read {name} from {file_path}: {exc}", file=sys.stderr)
        return default

    info = validate_encoding(file_path)
    parse_errors: list[str] = []
    for encoding in _encoding_candidates(info):
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError as exc:
            parse_errors.append(f"{encoding}: decode error ({exc})")
            continue

        try:
            parsed = _parse_json_text(text)
            if encoding != "utf-8" or info.get("warnings"):
                warning_suffix = f" warnings={info.get('warnings')}" if info.get("warnings") else ""
                print(
                    f"INFO: Loaded {name} from {file_path} using {encoding}{warning_suffix}",
                    file=sys.stderr,
                )
            return parsed
        except (json.JSONDecodeError, SyntaxError, ValueError) as exc:
            parse_errors.append(f"{encoding}: parse error ({exc})")
            continue

    print(
        f"WARNING: Could not load {name} from {file_path}: {'; '.join(parse_errors[-3:])}",
        file=sys.stderr,
    )
    return default


__all__ = [
    "clean_html",
    "load_json_robust",
    "load_text_robust",
    "sanitize_llm_json",
    "validate_encoding",
]
