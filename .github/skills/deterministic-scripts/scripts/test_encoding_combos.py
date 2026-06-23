#!/usr/bin/env python3
"""Combination and round-trip tests for deterministic script encoding behavior."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import encoding_utils


MINIMAL_UPSTREAM = {
    "pr_url": "https://dev.azure.com/org/proj/_git/repo/pullrequest/123",
    "code_review_findings": {"tier": "1", "important": [], "suggestions": []},
    "code_fix": {"fixes_applied": 0, "fix_commits": []},
    "risk_level": "low",
    "risk_signals": ["test only"],
    "gate_lint": "passed",
    "gate_build": "passed",
    "gate_test": "passed",
    "gate_security": "passed",
    "watch_and_fix": {
        "build_status": "passed",
        "fixes_pushed": 0,
        "fix_summaries": [],
        "fix_commits": [],
        "elapsed_minutes": 20,
    },
}


def load_script(filename: str, module_name: str | None = None):
    spec = importlib.util.spec_from_file_location(module_name or filename.replace("-", "_").replace(".py", ""), SCRIPTS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


BUILD_DIGEST_INPUT = load_script("build-digest-input.py", "build_digest_input_combo")
COMPOSE_DIGEST = load_script("compose-digest.py", "compose_digest_combo")
REVIEW_DIGEST = load_script("review-digest.py", "review_digest_combo")
SCRAPE_THREADS = load_script("scrape-threads.py", "scrape_threads_combo")
TRIAGE_THREADS = load_script("triage-threads.py", "triage_threads_combo")


class TestEncodingRoundTrips:
    def test_utf8_unicode_roundtrip(self, tmp_path):
        data = {"emoji": "😀", "cjk": "漢字", "rtl": "مرحبا", "hebrew": "שלום"}
        expected = json.dumps(data, ensure_ascii=False, sort_keys=True)
        source = tmp_path / "utf8.json"
        source.write_text(expected, encoding="utf-8")

        loaded = encoding_utils.load_json_robust(source, default=None)
        rewritten = tmp_path / "utf8-rewritten.json"
        rewritten.write_text(json.dumps(loaded, ensure_ascii=False, sort_keys=True), encoding="utf-8")

        assert loaded == data
        assert rewritten.read_text(encoding="utf-8") == expected

    def test_utf8_sig_roundtrip_bytes_stable(self, tmp_path):
        data = {"text": "BOM ✅ 漢字"}
        source = tmp_path / "utf8sig.json"
        source.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8-sig")

        loaded = encoding_utils.load_json_robust(source, default=None)
        rewritten = tmp_path / "utf8sig-rewritten.json"
        rewritten.write_text(json.dumps(loaded, ensure_ascii=False, sort_keys=True), encoding="utf-8-sig")

        assert loaded == data
        assert rewritten.read_bytes() == source.read_bytes()

    def test_utf16le_roundtrip_load_json_robust(self, tmp_path):
        data = {"text": "snowman ☃ and café"}
        source = tmp_path / "utf16le.json"
        source.write_bytes(b"\xff\xfe" + json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-16-le"))

        loaded = encoding_utils.load_json_robust(source, default=None)
        rewritten = tmp_path / "utf16le-rewritten.json"
        rewritten.write_text(json.dumps(loaded, ensure_ascii=False, sort_keys=True), encoding="utf-8")

        assert loaded == data
        assert encoding_utils.load_json_robust(rewritten, default=None) == data

    def test_utf16be_roundtrip_load_json_robust(self, tmp_path):
        data = {"text": "right-to-left שלום and emoji 🚀"}
        source = tmp_path / "utf16be.json"
        source.write_bytes(b"\xfe\xff" + json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-16-be"))

        loaded = encoding_utils.load_json_robust(source, default=None)
        rewritten = tmp_path / "utf16be-rewritten.json"
        rewritten.write_text(json.dumps(loaded, ensure_ascii=False, sort_keys=True), encoding="utf-8")

        assert loaded == data
        assert encoding_utils.load_json_robust(rewritten, default=None) == data


class TestEncodingCombinations:
    def test_utf16_with_html_entities_loads_and_cleans(self, tmp_path):
        payload = {"body": "Fish &amp; Chips &lt;tag&gt; &#x27;quoted&#x27;"}
        path = tmp_path / "utf16-entities.json"
        path.write_bytes(b"\xff\xfe" + json.dumps(payload, ensure_ascii=False).encode("utf-16-le"))

        loaded = encoding_utils.load_json_robust(path, default=None)

        assert loaded == payload
        assert encoding_utils.clean_html(loaded["body"]) == "Fish & Chips <tag> 'quoted'"

    def test_bom_with_llm_escapes_and_trailing_commas_loads(self, tmp_path):
        raw = "```json\n{\"quote\": \"it\\'s fine\", \"items\": [1, 2,],}\n```"
        path = tmp_path / "bom-llm.json"
        path.write_bytes(raw.encode("utf-8-sig"))

        loaded = encoding_utils.load_json_robust(path, default=None)

        assert loaded == {"quote": "it's fine", "items": [1, 2]}

    def test_cp1252_html_unicode_combo(self, tmp_path):
        payload = {"body": "<div>caf\u00e9 &euro; <b>bold</b></div>"}
        path = tmp_path / "cp1252-html.json"
        path.write_bytes(json.dumps(payload, ensure_ascii=False).encode("cp1252"))

        loaded = encoding_utils.load_json_robust(path, default=None)

        assert loaded == payload
        assert encoding_utils.clean_html(loaded["body"]) == "café € bold"

    def test_mixed_line_endings_bom_and_html(self, tmp_path):
        payload = {"body": "<div>Alpha</div>\r\n<p>Beta &amp; Co</p>\n<span>Gamma</span>"}
        path = tmp_path / "mixed-lines.json"
        path.write_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8-sig"))

        loaded = encoding_utils.load_json_robust(path, default=None)

        assert loaded == payload
        assert encoding_utils.clean_html(loaded["body"]) == "Alpha Beta & Co Gamma"


class TestApiEncodingEdges:
    def test_ado_thread_body_with_nested_divs_br_and_unicode(self):
        body = '<div style="padding:4px"><div><span style="color:red">Needs&nbsp;fix</span><br/>Use café 🚀</div></div>'
        assert encoding_utils.clean_html(body) == "Needs fix Use café 🚀"

    def test_github_comment_with_markdown_and_html_mix(self):
        body = "**Heads up:** <div><em>keep</em> this</div>\n- item"
        assert encoding_utils.clean_html(body) == "**Heads up:** keep this - item"

    def test_code_block_with_escaped_html_like_content_preserved(self):
        body = "<div>Before</div><br/>```html\n&lt;span&gt;safe&lt;/span&gt;\n```<div>After</div>"
        assert encoding_utils.clean_html(body) == "Before ```html <span>safe</span> ``` After"

    def test_thread_body_with_emoji_shortcodes_and_unicode(self):
        body = "<div>:rocket: shipped 🚀 &amp; ready</div>"
        assert encoding_utils.clean_html(body) == ":rocket: shipped 🚀 & ready"


class TestLLMOutputEdges:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ('{"ok": True, "flag": False, "missing": None}', {"ok": True, "flag": False, "missing": None}),
            ("{'status': 'ready', 'count': 2}", {"status": "ready", "count": 2}),
            ("```json\n{\"name\": \"combo\", \"items\": [1, 2]}\n```", {"name": "combo", "items": [1, 2]}),
            ('{"values": [1, 2,], "meta": {"ready": true,},}', {"values": [1, 2], "meta": {"ready": True}}),
        ],
    )
    def test_llm_outputs_parse_when_supported(self, tmp_path, raw, expected):
        path = tmp_path / "llm.json"
        path.write_text(raw, encoding="utf-8")
        assert encoding_utils.load_json_robust(path, default=None) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            '{\n  // comment\n  "value": 1\n}',
            '{/* block comment */ "value": 1}',
        ],
    )
    def test_llm_outputs_with_comments_fail_gracefully(self, tmp_path, raw):
        path = tmp_path / "llm-comments.json"
        path.write_text(raw, encoding="utf-8")
        assert encoding_utils.load_json_robust(path, default=None) is None

    def test_deeply_nested_json_with_encoding_issue_at_leaf(self, tmp_path):
        nested = leaf = {}
        for depth in range(12):
            leaf[f"level_{depth}"] = {}
            leaf = leaf[f"level_{depth}"]
        leaf["message"] = "caf&eacute; &amp; سلام"

        path = tmp_path / "deep.json"
        path.write_bytes(b"\xff\xfe" + json.dumps(nested, ensure_ascii=False).encode("utf-16-le"))

        loaded = encoding_utils.load_json_robust(path, default=None)
        current = loaded
        for depth in range(12):
            current = current[f"level_{depth}"]

        assert encoding_utils.clean_html(current["message"]) == "café & سلام"


class TestFailureModes:
    def test_binary_file_returns_none(self, tmp_path):
        path = tmp_path / "binary.bin"
        path.write_bytes(b"\x00\xff\x00\xfe\x80\x81not-json")
        assert encoding_utils.load_json_robust(path, default=None) is None

    def test_empty_file_returns_none(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("", encoding="utf-8")
        assert encoding_utils.load_json_robust(path, default=None) is None

    def test_whitespace_only_returns_none(self, tmp_path):
        path = tmp_path / "space.json"
        path.write_text("  \n\t  ", encoding="utf-8")
        assert encoding_utils.load_json_robust(path, default=None) is None

    def test_unreadable_file_returns_default(self, monkeypatch, tmp_path):
        path = tmp_path / "locked.json"
        path.write_text('{"ok": true}', encoding="utf-8")
        original = Path.read_bytes

        def raising_read_bytes(self):
            if self == path:
                raise PermissionError("locked for test")
            return original(self)

        monkeypatch.setattr(Path, "read_bytes", raising_read_bytes)
        assert encoding_utils.load_json_robust(path, default=None) is None

    def test_large_file_loads_without_data_loss(self, tmp_path):
        blob = "x" * (10 * 1024 * 1024 + 256) + "✅"
        path = tmp_path / "large.json"
        path.write_text(json.dumps({"blob": blob}, ensure_ascii=False), encoding="utf-8")

        loaded = encoding_utils.load_json_robust(path, default=None)

        assert loaded is not None
        assert len(loaded["blob"]) == len(blob)
        assert loaded["blob"].endswith("✅")


class TestCrossScriptEncodingConsistency:
    def test_upsert_style_utf8_json_is_readable_by_build_digest_input(self, tmp_path):
        path = tmp_path / "upsert-body.json"
        path.write_text(json.dumps({"content": "Digest ✅ café"}), encoding="utf-8")

        loaded = BUILD_DIGEST_INPUT._load_optional_json(str(path), "upsert-body")

        assert loaded == {"content": "Digest ✅ café"}

    def test_review_digest_upstream_file_is_readable_by_build_digest_input(self, tmp_path):
        upstream = REVIEW_DIGEST.build_upstream_data("", MINIMAL_UPSTREAM["pr_url"], "ado")
        upstream["code_review_findings"] = MINIMAL_UPSTREAM["code_review_findings"]
        upstream["code_fix"] = MINIMAL_UPSTREAM["code_fix"]
        upstream["risk_level"] = MINIMAL_UPSTREAM["risk_level"]
        upstream["risk_signals"] = MINIMAL_UPSTREAM["risk_signals"]
        upstream["gate_lint"] = MINIMAL_UPSTREAM["gate_lint"]
        upstream["gate_build"] = MINIMAL_UPSTREAM["gate_build"]
        upstream["gate_test"] = MINIMAL_UPSTREAM["gate_test"]
        upstream["gate_security"] = MINIMAL_UPSTREAM["gate_security"]
        upstream["watch_and_fix"] = MINIMAL_UPSTREAM["watch_and_fix"]

        path = tmp_path / "upstream-data.json"
        path.write_text(json.dumps(upstream, ensure_ascii=False, indent=2), encoding="utf-8")

        loaded = BUILD_DIGEST_INPUT._load_optional_json(str(path), "upstream")

        assert loaded["pr_url"] == MINIMAL_UPSTREAM["pr_url"]
        assert loaded["risk_signals"] == ["test only"]

    def test_scrape_threads_output_survives_shared_loader_roundtrip(self, tmp_path):
        output = {
            "threads": {
                "actionable": [{"thread_id": "1", "body": "<div>caf&eacute; ✅</div>"}],
                "resolved": [],
                "skipped": [],
            },
            "addressed_details": [{"thread_id": "1", "finding_summary": "caf&eacute; ✅", "commit_sha": "abc1234"}],
            "summary": {"total_threads": 1, "actionable": 1, "resolved": 0, "skipped": 0, "newly_resolved": 0},
        }
        path = tmp_path / "thread-state.json"
        SCRAPE_THREADS.write_output(output, str(path))

        first = encoding_utils.load_json_robust(path, default=None)
        rewritten = tmp_path / "triage-style.json"
        rewritten.write_text(json.dumps(first, ensure_ascii=False, indent=2), encoding="utf-8")
        second = encoding_utils.load_json_robust(rewritten, default=None)

        assert second["threads"]["actionable"][0]["body"] == "<div>caf&eacute; ✅</div>"
        assert encoding_utils.clean_html(second["threads"]["actionable"][0]["body"]) == "café ✅"

    def test_build_digest_input_output_is_readable_by_compose_digest(self, tmp_path):
        digest_input = BUILD_DIGEST_INPUT.build_digest_input(dict(MINIMAL_UPSTREAM))
        path = tmp_path / "digest-input.json"
        path.write_text(json.dumps(digest_input, ensure_ascii=False, indent=2), encoding="utf-8")

        loaded = encoding_utils.load_json_robust(path, default=None)
        digest = COMPOSE_DIGEST.compose(loaded)

        assert loaded["pr_url"] == MINIMAL_UPSTREAM["pr_url"]
        assert "PR Orchestrator" in digest
        assert "Review Digest" in digest

    def test_compose_digest_output_is_validated_by_review_digest(self, tmp_path):
        digest_input = BUILD_DIGEST_INPUT.build_digest_input(dict(MINIMAL_UPSTREAM))
        digest = COMPOSE_DIGEST.compose(digest_input)
        path = tmp_path / "digest.md"
        path.write_text(digest, encoding="utf-8")

        result = REVIEW_DIGEST.validate_digest(str(path))

        assert result["valid"] is True


class TestHtmlStrippingEdges:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("<div><span style='color:red'>text</span></div>", "text"),
            ("Alpha<br/>Beta<hr/>Gamma", "Alpha Beta Gamma"),
            ("&amp; &lt; &gt; &quot; &#39; &#x27;", "& < > \" ' '"),
            ("<div><span>broken</div>", "broken"),
            ("```html\n&lt;div&gt;safe&lt;/div&gt;\n```", "```html <div>safe</div> ```"),
            ("<div>one</div>   <span>two</span>\n\n<three>skip</three>", "one two skip"),
        ],
    )
    def test_clean_html_edge_cases(self, raw, expected):
        assert encoding_utils.clean_html(raw) == expected

    def test_triage_wrapper_uses_shared_html_cleaner(self):
        raw = "<div><span style='color:red'>text</span></div>"
        assert TRIAGE_THREADS.clean_thread_body(raw) == encoding_utils.clean_html(raw)
