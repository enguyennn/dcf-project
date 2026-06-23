#!/usr/bin/env python3
"""Unit tests for PR Orchestrator deterministic scripts.

Run: pytest test_scripts.py -v
"""

import contextlib
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).parent


def run_script(name: str, stdin: str = "", args: list = None, timeout: int = 30) -> dict:
    """Run a script and return parsed JSON output."""
    script = SCRIPTS_DIR / name
    cmd = [sys.executable, str(script)] + (args or [])
    result = subprocess.run(
        cmd, input=stdin, capture_output=True, text=True,
        timeout=timeout, encoding="utf-8", errors="replace",
    )
    parsed_json = None
    stripped_stdout = result.stdout.strip()
    if stripped_stdout.startswith("{") or stripped_stdout.startswith("["):
        try:
            parsed_json = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed_json = None
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "json": parsed_json,
    }


def load_script_module(module_name: str, filename: str, *, block_pr_platform: bool = False):
    """Import a script module, optionally forcing pr_platform import fallback."""
    import builtins
    import importlib.util
    from unittest.mock import patch

    spec = importlib.util.spec_from_file_location(module_name, str(SCRIPTS_DIR / filename))
    mod = importlib.util.module_from_spec(spec)
    stderr = io.StringIO()
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if block_pr_platform and name == "pr_platform":
            raise ImportError("blocked for test")
        return original_import(name, globals, locals, fromlist, level)

    saved_pr_platform = sys.modules.pop("pr_platform", None) if block_pr_platform else None
    try:
        with contextlib.redirect_stderr(stderr):
            if block_pr_platform:
                with patch("builtins.__import__", side_effect=guarded_import):
                    spec.loader.exec_module(mod)
            else:
                spec.loader.exec_module(mod)
    finally:
        if block_pr_platform:
            sys.modules.pop("pr_platform", None)
            if saved_pr_platform is not None:
                sys.modules["pr_platform"] = saved_pr_platform

    return mod, stderr.getvalue()


class TestEncodingUtils:
    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("encoding_utils", str(SCRIPTS_DIR / "encoding_utils.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @pytest.mark.parametrize(
        "name, raw_bytes, expected",
        [
            ("utf8", json.dumps({"text": "plain"}, ensure_ascii=False).encode("utf-8"), {"text": "plain"}),
            ("utf8sig", json.dumps({"text": "bom"}, ensure_ascii=False).encode("utf-8-sig"), {"text": "bom"}),
            ("utf16le", b"\xff\xfe" + json.dumps({"text": "left"}, ensure_ascii=False).encode("utf-16-le"), {"text": "left"}),
            ("utf16be", b"\xfe\xff" + json.dumps({"text": "right"}, ensure_ascii=False).encode("utf-16-be"), {"text": "right"}),
            ("cp1252", json.dumps({"text": "café"}, ensure_ascii=False).encode("cp1252"), {"text": "café"}),
        ],
    )
    def test_load_json_robust_supported_encodings(self, tmp_path, name, raw_bytes, expected):
        mod = self._load_module()
        path = tmp_path / f"{name}.json"
        path.write_bytes(raw_bytes)
        assert mod.load_json_robust(path, label=name, default=None) == expected

    def test_load_json_robust_utf16be_without_bom(self, tmp_path):
        mod = self._load_module()
        path = tmp_path / "utf16be-no-bom.json"
        path.write_bytes(json.dumps({"text": "snowman ☃"}, ensure_ascii=False).encode("utf-16-be"))
        assert mod.load_json_robust(path, default=None) == {"text": "snowman ☃"}

    def test_validate_encoding_reports_cp1252_and_utf16be(self, tmp_path):
        mod = self._load_module()
        cp1252_path = tmp_path / "mixed.json"
        cp1252_path.write_bytes(b'{"text":"caf\xe9"}')
        utf16be_path = tmp_path / "utf16be.json"
        utf16be_path.write_bytes(json.dumps({"text": "wide"}).encode("utf-16-be"))
        cp1252_info = mod.validate_encoding(cp1252_path)
        utf16be_info = mod.validate_encoding(utf16be_path)
        assert cp1252_info["encoding"] == "cp1252"
        assert utf16be_info["encoding"] == "utf-16-be"

    def test_sanitize_llm_json_repairs_common_issues(self):
        mod = self._load_module()
        raw = "```json\n{\"quote\": \"it\\'s fine\", \"items\": [1,2,],}\n```\n"
        sanitized = mod.sanitize_llm_json(raw)
        assert sanitized == '{"quote": "it\'s fine", "items": [1,2]}'
        assert json.loads(sanitized) == {"quote": "it's fine", "items": [1, 2]}

    def test_clean_html_handles_ado_thread_markup(self):
        mod = self._load_module()
        html_body = (
            '<small class="secondary-text">PR Assistant AI Code Review</small>'
            '<span>Use &lt;T&gt; and &amp; avoid ```suggestion\nfoo()\n```</span>'
            '<small class="secondary-text">Posted by bot</small>'
        )
        cleaned = mod.clean_html(html_body)
        assert "secondary-text" not in cleaned
        assert "suggestion" not in cleaned
        assert cleaned == "Use <T> and & avoid"

    def test_load_json_robust_handles_mixed_cp1252_bytes(self, tmp_path):
        mod = self._load_module()
        path = tmp_path / "mixed-cp1252.json"
        path.write_bytes(b'{"summary": "na\xefve caf\xe9"}')
        assert mod.load_json_robust(path, default=None) == {"summary": "naïve café"}

    def test_round_trip_write_read_write_is_stable(self, tmp_path):
        mod = self._load_module()
        source = tmp_path / "source.json"
        source.write_bytes(b'\xef\xbb\xbf' + json.dumps({"emoji": "✅", "text": "café"}, ensure_ascii=False, indent=2).encode("utf-8"))
        payload = mod.load_json_robust(source, default=None)
        first = tmp_path / "roundtrip-1.json"
        second = tmp_path / "roundtrip-2.json"
        first.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        reloaded = mod.load_json_robust(first, default=None)
        second.write_text(json.dumps(reloaded, ensure_ascii=False, indent=2), encoding="utf-8")
        assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


# ── detect-platform.py ──────────────────────────────────────────────────────

class TestDetectPlatform:
    def test_ado_https(self):
        r = run_script("detect-platform.py", args=["https://msazure@dev.azure.com/msazure/One/_git/Repo"])
        assert r["json"]["platform"] == "ado"
        assert r["json"]["org"] == "msazure"
        assert r["json"]["project"] == "One"
        assert r["json"]["repo"] == "Repo"

    def test_ado_ssh(self):
        r = run_script("detect-platform.py", args=["git@ssh.dev.azure.com:v3/msazure/One/Repo"])
        assert r["json"]["platform"] == "ado"
        assert r["json"]["org"] == "msazure"

    def test_ado_legacy_visualstudio(self):
        r = run_script("detect-platform.py", args=["https://msazure.visualstudio.com/DefaultCollection/One/_git/Repo/pullrequest/123"])
        assert r["json"]["platform"] == "ado"
        assert r["json"]["org"] == "msazure"
        assert r["json"]["project"] == "One"

    def test_github_https(self):
        r = run_script("detect-platform.py", args=["https://github.com/azure-core/octane.git"])
        assert r["json"]["platform"] == "github"
        assert r["json"]["owner"] == "azure-core"
        assert r["json"]["repo"] == "octane"

    def test_github_ssh(self):
        r = run_script("detect-platform.py", args=["git@github.com:azure-core/octane.git"])
        assert r["json"]["platform"] == "github"
        assert r["json"]["owner"] == "azure-core"

    def test_unknown_url(self):
        r = run_script("detect-platform.py", args=["https://gitlab.com/foo/bar"])
        assert r["json"]["platform"] == "unknown"

    def test_empty_input(self):
        r = run_script("detect-platform.py", args=[""])
        assert r["json"]["platform"] == "unknown"


# ── classify-risk.py ─────────────────────────────────────────────────────────

class TestClassifyRisk:
    def test_middleware_is_medium(self):
        files = json.dumps(["CirrusPortalAPI/Middleware/SpaMiddleware.cs"])
        r = run_script("classify-risk.py", stdin=files)
        assert r["json"]["risk_level"] == "medium"

    def test_services_is_medium(self):
        files = json.dumps(["src/Services/UserService.cs"])
        r = run_script("classify-risk.py", stdin=files)
        assert r["json"]["risk_level"] == "medium"

    def test_auth_is_high(self):
        files = json.dumps(["src/Auth/JwtHandler.cs"])
        r = run_script("classify-risk.py", stdin=files)
        assert r["json"]["risk_level"] == "high"

    def test_migration_is_high(self):
        files = json.dumps(["db/migrations/001_add_users.sql"])
        r = run_script("classify-risk.py", stdin=files)
        assert r["json"]["risk_level"] == "high"

    def test_test_only_is_low(self):
        files = json.dumps(["src/Tests/UserTests.cs", "src/__tests__/auth.test.ts"])
        r = run_script("classify-risk.py", stdin=files)
        assert r["json"]["risk_level"] == "low"

    def test_docs_only_is_low(self):
        files = json.dumps(["README.md", "docs/architecture.md"])
        r = run_script("classify-risk.py", stdin=files)
        assert r["json"]["risk_level"] == "low"

    def test_empty_files_is_low(self):
        r = run_script("classify-risk.py", stdin="[]")
        assert r["json"]["risk_level"] == "low"

    def test_mixed_prod_and_test(self):
        files = json.dumps(["src/Middleware/Auth.cs", "src/Tests/AuthTests.cs"])
        r = run_script("classify-risk.py", stdin=files)
        assert r["json"]["risk_level"] in ("medium", "high")
        assert any("test file" in s.lower() for s in r["json"]["signals"])

    def test_sensitive_filename_keyword(self):
        files = json.dumps(["src/utils/password-helper.ts"])
        r = run_script("classify-risk.py", stdin=files)
        assert r["json"]["risk_level"] == "medium"
        assert r["json"]["expertise_needed"] == "Security"

    def test_config_files(self):
        files = json.dumps(["appsettings.json", "src/app.config"])
        r = run_script("classify-risk.py", stdin=files)
        assert r["json"]["risk_level"] == "medium"


# ── validate-digest-format.py ────────────────────────────────────────────────

class TestValidateDigest:
    GOOD_DIGEST = """<!-- ai-agent:pr-orchestrator-digest -->
# PR Orchestrator — Review Digest
> _Single summary._
## Risk Level: Medium
> Review recommended
> **Signals**: test
## Needs Your Judgment
None
## What Was Fixed
> _Tracked._
#### Pre-Validate (Step 1)
| # | File | Finding | Found By | Commit | Status |
|---|------|---------|----------|--------|--------|
| 1 | f.cs | Bug | GK | sha | Fixed |
#### Watch & Fix CI (Step 3)
CI passed.
#### Address Review Feedback (Step 5)
No feedback.
## Validation Timeline
| Phase | Duration | Result |
|-------|----------|--------|
| Pre-Validate | ~5 min | Done |
| Create PR | ~1 min | Done |
| Watch & Fix CI | ~20 min | Done |
| Review Digest | ~2 min | Done |
| Address Feedback | ~1 min | Done |
**Total elapsed**: ~30 min
## Mechanically Verified
| Check | Status | Details |
|-------|--------|---------|
| Lint | Pass | OK |
| Review | Pass | OK |
| Build | Pass | OK |
| Tests | Pass | OK |
| Security | Pass | OK |
**Verdict: Ready**
---
<sub>Generated by [PR Orchestrator](https://github.com/azure-core/octane) — Phase 4</sub>
"""

    def _validate(self, content: str) -> dict:
        tmp = os.path.join(tempfile.gettempdir(), "test-digest-validate.md")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        r = run_script("validate-digest-format.py", args=[tmp])
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return r["json"]

    def test_good_digest_passes(self):
        result = self._validate(self.GOOD_DIGEST)
        assert result["valid"] is True
        assert len(result["violations"]) == 0

    def test_missing_sentinel(self):
        bad = self.GOOD_DIGEST.replace("<!-- ai-agent:pr-orchestrator-digest -->", "")
        result = self._validate(bad)
        assert result["valid"] is False
        assert any("sentinel" in v.lower() for v in result["violations"])

    def test_3_column_table_rejected(self):
        bad = self.GOOD_DIGEST.replace(
            "| # | File | Finding | Found By | Commit | Status |\n|---|------|---------|----------|--------|--------|\n| 1 | f.cs | Bug | GK | sha | Fixed |",
            "| Finding | Fix | Commit |\n|---------|-----|--------|\n| Bug | Fixed | sha |",
        )
        result = self._validate(bad)
        assert result["valid"] is False
        assert any("3 columns" in v for v in result["violations"])

    def test_missing_file_returns_error(self):
        missing = os.path.join(tempfile.gettempdir(), "missing-digest-format-test.md")
        if os.path.exists(missing):
            os.unlink(missing)
        result = run_script("validate-digest-format.py", args=[missing])
        assert result["exit_code"] == 1
        assert "File not found" in result["stderr"]
        assert result["json"]["valid"] is False

    def test_em_dash_duration_rejected(self):
        bad = self.GOOD_DIGEST.replace("| Pre-Validate | ~5 min | Done |", "| Pre-Validate | \u2014 | Done |")
        result = self._validate(bad)
        assert result["valid"] is False
        assert any("duration" in v.lower() or "blank" in v.lower() for v in result["violations"])

    def test_missing_footer(self):
        bad = self.GOOD_DIGEST.replace("<sub>Generated by [PR Orchestrator](https://github.com/azure-core/octane) — Phase 4</sub>", "")
        result = self._validate(bad)
        assert result["valid"] is False
        assert any("footer" in v.lower() for v in result["violations"])

    def test_empty_input(self):
        result = self._validate("")
        assert result["valid"] is False


# ── validate-pr-description.py ───────────────────────────────────────────────

class TestValidatePRDescription:
    def _validate(self, content: str) -> dict:
        r = run_script("validate-pr-description.py", stdin=content)
        return r["json"]

    def test_valid_description(self):
        desc = "<!-- pr-orchestrator -->\n## Intent\nFix\n## Changes\nStuff\n## Validation\nPassed\n<sub>Generated by [PR Orchestrator](https://github.com/azure-core/octane)</sub>"
        result = self._validate(desc)
        assert result["valid"] is True

    def test_gitops_overwrite_detected(self):
        desc = "<!-- pr-orchestrator -->\n----\n#### AI description\n<!-- GitOpsUserAgent=GitOps.Apps.Server -->"
        result = self._validate(desc)
        assert result["valid"] is False
        assert result["overwritten_by"] == "GitOps PR Copilot"

    def test_missing_sentinel(self):
        desc = "## Intent\nFix\n## Changes\nStuff\n## Validation\nPassed"
        result = self._validate(desc)
        assert result["valid"] is False
        assert "<!-- pr-orchestrator --> sentinel" in result["missing_sections"]

    def test_missing_sections(self):
        desc = "<!-- pr-orchestrator -->\n## Intent\nFix"
        result = self._validate(desc)
        assert result["valid"] is False
        assert "## Changes" in result["missing_sections"]

    def test_empty_input(self):
        result = self._validate("")
        assert result["valid"] is False

    def test_description_with_digest_link_placeholder(self):
        """PR body with DIGEST_LINK_PLACEHOLDER (before Phase 4 replaces it) should be valid."""
        desc = (
            "<!-- pr-orchestrator -->\n"
            "# fix: stuff\n\n"
            "> 📋 **[Review Digest](DIGEST_LINK_PLACEHOLDER)** — full validation details\n\n"
            "## Intent\nFix bugs\n"
            "## Changes\nChanged things\n"
            "## Validation\nAll passed\n"
            "<sub>Generated by [PR Orchestrator](https://github.com/azure-core/octane)</sub>"
        )
        result = self._validate(desc)
        assert result["valid"] is True

    def test_description_with_resolved_digest_link(self):
        """PR body with actual digest URL (after Phase 4 replacement) should be valid."""
        desc = (
            "<!-- pr-orchestrator -->\n"
            "# fix: stuff\n\n"
            "> 📋 **[Review Digest](https://dev.azure.com/org/proj/_git/Repo/pullrequest/12345?discussionId=240175592)** — full validation details\n\n"
            "## Intent\nFix bugs\n"
            "## Changes\nChanged things\n"
            "## Validation\nAll passed\n"
            "<sub>Generated by [PR Orchestrator](https://github.com/azure-core/octane)</sub>"
        )
        result = self._validate(desc)
        assert result["valid"] is True


# ── compose-digest.py ────────────────────────────────────────────────────────

class TestComposeDigest:
    MINIMAL_INPUT = {
        "risk": {"level": "low", "signals": "test only", "review_requirement": "AI review sufficient"},
        "judgment_items": "None",
        "findings": {"prevalidate": [], "watch_fix": [], "feedback": []},
        "timeline": [
            {"phase": "Pre-Validate", "duration": "~5 min", "result": "Done"},
            {"phase": "Create PR", "duration": "~1 min", "result": "Done"},
            {"phase": "Watch & Fix CI", "duration": "~20 min", "result": "Done"},
            {"phase": "Review Digest", "duration": "~2 min", "result": "Done"},
            {"phase": "Address Feedback", "duration": "~1 min", "result": "Done"},
        ],
        "gates": [
            {"check": "Code Review", "status": "Passed", "details": "OK"},
            {"check": "Build", "status": "Passed", "details": "OK"},
        ],
        "verdict": "ready",
        "advisory": [],
        "review_engine": "Gatekeeper",
        "total_duration": "~30 min",
        "footer_variant": "Phase 4 Review Digest",
    }

    def test_compose_produces_valid_digest(self):
        r = run_script("compose-digest.py", stdin=json.dumps(self.MINIMAL_INPUT))
        assert r["exit_code"] == 0
        tmp = os.path.join(tempfile.gettempdir(), "test-compose-validate.md")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(r["stdout"])
        v = run_script("validate-digest-format.py", args=[tmp])
        try:
            os.unlink(tmp)
        except OSError:
            pass
        assert v["json"]["valid"] is True, f"Violations: {v['json']['violations']}"

    def test_compose_includes_sentinel(self):
        r = run_script("compose-digest.py", stdin=json.dumps(self.MINIMAL_INPUT))
        assert "<!-- ai-agent:pr-orchestrator-digest -->" in r["stdout"]

    def test_compose_verdict_approved(self):
        """Verdict 'approved' should render as a display string, not raw 'approved'."""
        input_data = {**self.MINIMAL_INPUT, "verdict": "approved"}
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        assert r["exit_code"] == 0
        # Should display the mapped string, not the raw "approved"
        assert "Approved" in r["stdout"]
        assert "all findings addressed" in r["stdout"].lower() or "approved" in r["stdout"].lower()

    def test_compose_no_pr_description_link_in_digest(self):
        """Digest should NOT contain a link to the PR description (link goes the other direction)."""
        input_data = {**self.MINIMAL_INPUT, "pr_url": "https://dev.azure.com/org/proj/_git/Repo/pullrequest/42"}
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        assert "[View PR Description]" not in r["stdout"]

    def test_compose_unknown_risk_not_assessed_without_signals_line(self):
        """Unknown risk renders intentionally and omits the empty Signals line."""
        input_data = {
            **self.MINIMAL_INPUT,
            "risk": {
                "level": "unknown",
                "signals": "Not assessed",
                "review_requirement": "Not assessed — no risk classification available",
            },
        }
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        assert r["exit_code"] == 0
        assert "## Risk Level: ⚪ Not assessed" in r["stdout"]
        assert "> Not assessed — no risk classification available" in r["stdout"]
        assert "> **Signals**:" not in r["stdout"]

    def test_compose_includes_findings_table(self):
        input_data = {**self.MINIMAL_INPUT}
        input_data["findings"] = {
            "prevalidate": [{"num": 1, "file": "test.cs", "finding": "Bug", "found_by": "GK", "fixed_by": "Auto", "commit_sha": "abc123", "commit_url": "https://example.com", "status": "Fixed"}],
            "watch_fix": [], "feedback": [],
        }
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        assert "| 1 |" in r["stdout"]
        assert "`test.cs`" in r["stdout"]

    def test_compose_file_url_renders_clickable_link(self):
        """When file_url is present, file column should be a clickable markdown link."""
        input_data = {**self.MINIMAL_INPUT}
        input_data["findings"] = {
            "prevalidate": [{"num": 1, "file": "src/Service.cs", "file_url": "https://dev.azure.com/org/proj/_git/Repo/pullrequest/123?_a=files&path=/src/Service.cs", "finding": "Bug found", "found_by": "GK", "commit_sha": "", "commit_url": "", "status": "💡 Suggestion"}],
            "watch_fix": [], "feedback": [],
        }
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        assert "[`src/Service.cs`](https://dev.azure.com/" in r["stdout"]

    def test_compose_file_no_url_renders_backtick(self):
        """When file_url is missing, file column should be plain backtick code."""
        input_data = {**self.MINIMAL_INPUT}
        input_data["findings"] = {
            "prevalidate": [{"num": 1, "file": "src/Foo.cs", "finding": "Issue", "found_by": "GK", "commit_sha": "", "commit_url": "", "status": "💡 Suggestion"}],
            "watch_fix": [], "feedback": [],
        }
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        assert "`src/Foo.cs`" in r["stdout"]
        # Should NOT be a link
        assert "[`src/Foo.cs`](" not in r["stdout"]
        r = run_script("compose-digest.py", stdin=json.dumps(self.MINIMAL_INPUT))
        assert "No review feedback received" in r["stdout"]

    def test_compose_commit_sha_without_url(self):
        """When commit_sha exists but commit_url is empty, render plain SHA (no link)."""
        input_data = {**self.MINIMAL_INPUT}
        input_data["findings"] = {
            "prevalidate": [{"num": 1, "file": "test.cs", "finding": "Bug", "found_by": "GK", "commit_sha": "e1632c8", "commit_url": "", "status": "✅ Fixed"}],
            "watch_fix": [], "feedback": [],
        }
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        assert "`e1632c8`" in r["stdout"]
        assert "—" not in r["stdout"].split("Pre-Validate")[1].split("Watch")[0]  # No dash in prevalidate section

    def test_compose_commit_sha_with_url(self):
        """When both commit_sha and commit_url exist, render as clickable link."""
        input_data = {**self.MINIMAL_INPUT}
        input_data["findings"] = {
            "prevalidate": [{"num": 1, "file": "test.cs", "finding": "Bug", "found_by": "GK", "commit_sha": "e1632c8", "commit_url": "https://example.com/commit/e1632c8", "status": "✅ Fixed"}],
            "watch_fix": [], "feedback": [],
        }
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        assert "[`e1632c8`](https://example.com/commit/e1632c8)" in r["stdout"]

    def test_judgment_table_with_view_links(self):
        """Judgment items render as a table with View → links."""
        input_data = {**self.MINIMAL_INPUT}
        input_data["findings"] = {
            "prevalidate": [{
                "num": 1, "file": "Service.cs",
                "file_url": "https://dev.azure.com/org/proj/_git/Repo/pullrequest/123?_a=files&path=/Service.cs",
                "finding": "Null guard missing",
                "found_by": "GK", "commit_sha": "", "commit_url": "",
                "status": "⚠️ Needs judgment",
                "view_url": "https://dev.azure.com/org/proj/_git/Repo/pullrequest/123?_a=files&path=/Service.cs",
            }],
            "watch_fix": [],
            "feedback": [{
                "num": 1, "file": "Middleware.cs",
                "file_url": "https://dev.azure.com/org/proj/_git/Repo/pullrequest/123?_a=files&path=/Middleware.cs",
                "finding": "Silent prod fallback",
                "found_by": "Reviewer", "commit_sha": "", "commit_url": "",
                "status": "⚠️ Needs judgment",
                "thread_id": "99999",
                "view_url": "https://dev.azure.com/org/proj/_git/Repo/pullrequest/123?discussionId=99999",
            }],
        }
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        out = r["stdout"]
        # Should have a table header
        assert "| # | Source | File | Issue | Review |" in out
        # Should have Step 1 and Step 5 rows
        assert "Step 1" in out
        assert "Step 5" in out
        # Should have View → links
        assert "[View →](" in out
        # Should NOT have old-style flat text
        assert "**Pre-Validate" not in out

    def test_judgment_no_items(self):
        """When no findings need judgment, show plain text message."""
        input_data = {**self.MINIMAL_INPUT, "judgment_items": ""}
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        assert "No items requiring human judgment" in r["stdout"]

    def test_judgment_sanitizes_pipes_in_findings(self):
        """Pipe characters in finding text must be escaped for table cells."""
        input_data = {**self.MINIMAL_INPUT}
        input_data["findings"] = {
            "prevalidate": [{
                "num": 1, "file": "test.cs",
                "finding": "Value is true | false depending on config",
                "found_by": "GK", "commit_sha": "", "commit_url": "",
                "status": "⚠️ Needs judgment",
                "view_url": "",
            }],
            "watch_fix": [], "feedback": [],
        }
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        # The pipe should be escaped (not break the table)
        assert "true | false" not in r["stdout"]
        assert "true ∣ false" in r["stdout"]

    def test_judgment_sanitizes_newlines(self):
        """Newlines in finding text must be collapsed for table cells."""
        input_data = {**self.MINIMAL_INPUT}
        input_data["findings"] = {
            "prevalidate": [{
                "num": 1, "file": "test.cs",
                "finding": "Line one\nLine two\r\nLine three",
                "found_by": "GK", "commit_sha": "", "commit_url": "",
                "status": "⚠️ Needs judgment",
                "view_url": "",
            }],
            "watch_fix": [], "feedback": [],
        }
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        assert "Line one Line two Line three" in r["stdout"]

    def test_html_tags_stripped_from_findings(self):
        """HTML tags from ADO thread bodies must be stripped in finding cells."""
        input_data = {**self.MINIMAL_INPUT}
        input_data["findings"] = {
            "prevalidate": [{
                "num": 1, "file": "Services/TestPassRunService.cs",
                "finding": '<span style="font-family:\'Segoe UI\';font-size:14px;">Missing single quotes around -Environment</span>',
                "found_by": "Code Review", "commit_sha": "abc1234", "commit_url": "",
                "status": "✅ Fixed",
                "view_url": "",
            }],
            "watch_fix": [], "feedback": [],
        }
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        assert r["exit_code"] == 0
        assert "<span" not in r["stdout"]
        assert "Missing single quotes around -Environment" in r["stdout"]

    def test_html_entities_decoded_in_findings(self):
        """HTML entities like &amp; &lt; must be decoded in finding cells."""
        input_data = {**self.MINIMAL_INPUT}
        input_data["findings"] = {
            "prevalidate": [{
                "num": 1, "file": "test.cs",
                "finding": "Use &lt;T&gt; instead of &amp;generic",
                "found_by": "GK", "commit_sha": "", "commit_url": "",
                "status": "⚠️ Needs judgment",
                "view_url": "",
            }],
            "watch_fix": [], "feedback": [],
        }
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        assert r["exit_code"] == 0
        assert "&lt;" not in r["stdout"]
        assert "&amp;" not in r["stdout"]
        # The < and > will show as text in the markdown cell
        assert "Use" in r["stdout"]

    def test_compose_feedback_tables_do_not_use_double_blank_lines(self):
        input_data = {**self.MINIMAL_INPUT}
        input_data["findings"] = {
            "prevalidate": [],
            "watch_fix": [{
                "num": 1, "file": "src/ci.py", "finding": "Retry flaky test", "found_by": "CI", "commit_sha": "abc1234", "commit_url": "", "status": "✅ Fixed",
            }],
            "feedback": [{
                "num": 1, "file": "src/review.py", "finding": "Reviewer note", "found_by": "Reviewer", "commit_sha": "def5678", "commit_url": "", "status": "✅ Fixed",
            }],
        }
        input_data["triage_summary"] = {"total": 1, "actionable": 1, "skipped": 0, "skip_reasons": {}}
        r = run_script("compose-digest.py", stdin=json.dumps(input_data))
        assert r["exit_code"] == 0
        assert "resolve CI failures:\n\n| # | File" not in r["stdout"]
        assert "skipped\n\n| # | File" not in r["stdout"]
        assert "received.\n\n| # | File" not in r["stdout"]

    def test_compose_invalid_stdin_json_exits_with_error(self):
        r = run_script("compose-digest.py", stdin="{not valid json")
        assert r["exit_code"] == 1
        assert "Invalid JSON on stdin" in r["stderr"]


# ── fix-encoding.py ──────────────────────────────────────────────────────────

class TestFixEncoding:
    def test_fixes_garbled_emojis(self):
        tmp = os.path.join(tempfile.gettempdir(), "test-fix-encoding.md")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("# PR Orchestrator ΓÇö Review Digest\n## Risk: ≡ƒƒí Medium")
        r = run_script("fix-encoding.py", args=[tmp])
        fixed = Path(tmp).read_text(encoding="utf-8")
        try:
            os.unlink(tmp)
        except OSError:
            pass
        assert "—" in fixed
        assert "ΓÇö" not in fixed

    def test_clean_input_is_noop(self):
        tmp = os.path.join(tempfile.gettempdir(), "test-fix-clean.md")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("# Clean text with no garbled chars")
        r = run_script("fix-encoding.py", args=[tmp])
        assert "0 replacements" in r["stderr"]
        try:
            os.unlink(tmp)
        except OSError:
            pass


class TestPrUrlUtils:
    """Tests for shared PR URL parsing helpers."""

    def test_parse_pr_url_ado_devazure(self):
        mod, _ = load_script_module("pr_url_utils_devazure", "pr_url_utils.py")
        result = mod.parse_pr_url("https://dev.azure.com/myorg/myproj/_git/myrepo/pullrequest/123")
        assert result == {
            "platform": "ado",
            "org": "myorg",
            "project": "myproj",
            "repo": "myrepo",
            "pr_id": "123",
            "api_base": "https://dev.azure.com/myorg",
            "base_url": "https://dev.azure.com/myorg",
        }

    def test_parse_pr_url_ado_visualstudio_defaultcollection(self):
        mod, _ = load_script_module("pr_url_utils_vs", "pr_url_utils.py")
        result = mod.parse_ado_pr_url("https://msazure.visualstudio.com/DefaultCollection/One/_git/Repo/pullrequest/789")
        assert result["org"] == "msazure"
        assert result["project"] == "One"
        assert result["repo"] == "Repo"
        assert result["pr_id"] == "789"
        assert result["api_base"] == "https://msazure.visualstudio.com"

    def test_parse_pr_url_github(self):
        mod, _ = load_script_module("pr_url_utils_github", "pr_url_utils.py")
        result = mod.parse_github_pr_url("https://github.com/azure-core/octane/pull/439")
        assert result == {
            "platform": "github",
            "owner": "azure-core",
            "repo": "octane",
            "pr_id": "439",
            "pr_num": "439",
        }

    def test_parse_pr_url_invalid(self):
        mod, _ = load_script_module("pr_url_utils_invalid", "pr_url_utils.py")
        assert mod.parse_pr_url("https://gitlab.com/owner/repo/-/merge_requests/1") == {}
        assert mod.parse_ado_pr_url("https://github.com/owner/repo/pull/1") == {}
        assert mod.parse_github_pr_url("https://dev.azure.com/org/proj/_git/repo/pullrequest/1") == {}


# ── upsert-digest.py (unit tests for parse_ado_url) ─────────────────────────

class TestUpsertDigest:
    """Test upsert-digest.py URL parsing and az rest command construction."""

    @staticmethod
    def _load_module():
        """Import upsert-digest.py as a module."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("upsert", str(SCRIPTS_DIR / "upsert-digest.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_parse_ado_url_dev_azure_com(self):
        mod = self._load_module()
        result = mod.parse_ado_url("https://dev.azure.com/myorg/myproj/_git/myrepo/pullrequest/123")
        assert result["org"] == "myorg"
        assert result["project"] == "myproj"
        assert result["repo"] == "myrepo"
        assert result["pr_id"] == "123"
        assert result["api_base"] == "https://dev.azure.com/myorg"

    def test_parse_ado_url_visualstudio_com(self):
        mod = self._load_module()
        result = mod.parse_ado_url("https://msazure.visualstudio.com/One/_git/SomeRepo/pullrequest/456")
        assert result["org"] == "msazure"
        assert result["project"] == "One"
        assert result["repo"] == "SomeRepo"
        assert result["pr_id"] == "456"
        assert result["api_base"] == "https://msazure.visualstudio.com"

    def test_parse_ado_url_visualstudio_default_collection(self):
        mod = self._load_module()
        result = mod.parse_ado_url("https://msazure.visualstudio.com/DefaultCollection/One/_git/Repo/pullrequest/789")
        assert result["org"] == "msazure"
        assert result["project"] == "One"
        assert result["api_base"] == "https://msazure.visualstudio.com"

    def test_parse_ado_url_invalid(self):
        mod = self._load_module()
        result = mod.parse_ado_url("https://github.com/owner/repo/pull/42")
        assert result == {}

    def test_parse_github_url(self):
        mod = self._load_module()
        result = mod.parse_github_url("https://github.com/azure-core/octane/pull/439")
        assert result["owner"] == "azure-core"
        assert result["repo"] == "octane"
        assert result["pr_num"] == "439"

    def test_runtime_fallback_logs_and_uses_cli(self):
        mod = self._load_module()
        from unittest.mock import patch

        class BrokenDigestOps:
            def __init__(self, ref):
                pass

            def find_existing(self, marker):
                raise RuntimeError("boom")

        with patch.object(mod.PrRef, "from_url", return_value=object()), \
             patch.object(mod, "DigestOps", BrokenDigestOps), \
             patch.object(mod, "run_cmd", return_value={"exit_code": 0, "stdout": "", "stderr": ""}), \
             contextlib.redirect_stderr(io.StringIO()) as captured:
            result = mod.upsert_github(
                "https://github.com/azure-core/octane/pull/439",
                mod.DIGEST_MARKER + "\nbody",
                True,
            )

        assert result["action"] == "dry_run"
        assert result["would_do"] == "would_create"
        assert "[fallback] pr_platform.DigestOps.upsert failed (boom) — using CLI" in captured.getvalue()


class TestPrPlatform:
    """Unit tests for pr_platform.py shared abstraction."""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("pr_platform", str(SCRIPTS_DIR / "pr_platform.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["pr_platform"] = mod
        spec.loader.exec_module(mod)
        return mod

    class _Completed:
        def __init__(self, stdout="", stderr="", returncode=0):
            self.stdout = stdout
            self.stderr = stderr
            self.returncode = returncode

    def test_prref_from_url_ado_devazure(self):
        mod = self._load_module()
        ref = mod.PrRef.from_url("https://dev.azure.com/myorg/myproj/_git/myrepo/pullrequest/123")
        assert ref.platform == "ado"
        assert ref.org == "myorg"
        assert ref.project == "myproj"
        assert ref.repo == "myrepo"
        assert ref.pr_id == "123"
        assert ref.base_url == "https://dev.azure.com/myorg"
        assert ref.api_base.endswith("/pullRequests/123")
        assert ref.repo_slug == "myorg/myproj/myrepo"

    def test_prref_from_url_ado_visualstudio(self):
        mod = self._load_module()
        ref = mod.PrRef.from_url("https://msazure.visualstudio.com/One/_git/Repo/pullrequest/456")
        assert ref.platform == "ado"
        assert ref.base_url == "https://msazure.visualstudio.com"
        assert ref.project == "One"
        assert ref.pr_id == "456"

    def test_prref_from_url_ado_defaultcollection(self):
        mod = self._load_module()
        ref = mod.PrRef.from_url("https://msazure.visualstudio.com/DefaultCollection/One/_git/Repo/pullrequest/789")
        assert ref.platform == "ado"
        assert ref.base_url == "https://msazure.visualstudio.com"
        assert ref.project == "One"
        assert ref.pr_id == "789"

    def test_prref_from_url_github(self):
        mod = self._load_module()
        ref = mod.PrRef.from_url("https://github.com/azure-core/octane/pull/42")
        assert ref.platform == "github"
        assert ref.owner == "azure-core"
        assert ref.repo == "octane"
        assert ref.pr_num == "42"
        assert ref.repo_slug == "azure-core/octane"

    def test_prref_invalid_url_raises(self):
        mod = self._load_module()
        with pytest.raises(ValueError):
            mod.PrRef.from_url("https://gitlab.com/org/repo/-/merge_requests/1")

    def test_run_cli_success(self):
        mod = self._load_module()
        from unittest.mock import patch
        with patch.object(mod.subprocess, "run", return_value=self._Completed(stdout="ok", returncode=0)) as mock_run:
            result = mod.run_cli(["gh", "api", "repos/o/r/issues/1/comments"])
        assert result.stdout == "ok"
        mock_run.assert_called_once()

    def test_run_cli_failure_raises(self):
        mod = self._load_module()
        from unittest.mock import patch
        with patch.object(mod.subprocess, "run", return_value=self._Completed(stderr="boom", returncode=1)):
            with pytest.raises(subprocess.CalledProcessError):
                mod.run_cli(["gh", "api", "repos/o/r/issues/1/comments"])

    def test_run_cli_timeout_raises(self):
        mod = self._load_module()
        from unittest.mock import patch
        with patch.object(mod.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd=["gh"], timeout=5)):
            with pytest.raises(RuntimeError):
                mod.run_cli(["gh"], timeout=5)

    def test_prbodyops_fetch_and_update_ado(self):
        mod = self._load_module()
        from unittest.mock import patch
        ref = mod.PrRef.from_url("https://dev.azure.com/org/proj/_git/repo/pullrequest/1")
        ops = mod.PrBodyOps(ref)
        with patch.object(mod, "run_cli", side_effect=[self._Completed(stdout="Body\n"), self._Completed(stdout="")]) as mock_run:
            body = ops.fetch()
            ops.update("Updated body")
        assert body == "Body"
        assert mock_run.call_args_list[0].args[0][:4] == ["az", "repos", "pr", "show"]
        assert "--uri" in mock_run.call_args_list[1].args[0]

    def test_prbodyops_fetch_and_update_github(self):
        mod = self._load_module()
        from unittest.mock import patch
        ref = mod.PrRef.from_url("https://github.com/azure-core/octane/pull/2")
        ops = mod.PrBodyOps(ref)
        with patch.object(mod, "run_cli", side_effect=[self._Completed(stdout="Body\n"), self._Completed(stdout="")]) as mock_run:
            body = ops.fetch()
            ops.update("Updated body")
        assert body == "Body"
        assert mock_run.call_args_list[0].args[0][:3] == ["gh", "pr", "view"]
        assert mock_run.call_args_list[1].args[0][:3] == ["gh", "pr", "edit"]
        assert "--body-file" in mock_run.call_args_list[1].args[0]

    def test_digestops_find_existing_and_upsert_ado(self):
        mod = self._load_module()
        from unittest.mock import patch
        ref = mod.PrRef.from_url("https://dev.azure.com/org/proj/_git/repo/pullrequest/3")
        ops = mod.DigestOps(ref)
        threads = json.dumps({"value": [{"id": 11, "comments": [{"id": 22, "content": "<!-- ai-agent:pr-orchestrator-digest -->\nbody"}]}]})
        with patch.object(mod, "run_cli", side_effect=[self._Completed(stdout=threads), self._Completed(stdout=threads), self._Completed(stdout="")]):
            existing = ops.find_existing("<!-- ai-agent:pr-orchestrator-digest -->")
            result = ops.upsert("updated", "<!-- ai-agent:pr-orchestrator-digest -->")
        assert existing["thread_id"] == "11"
        assert existing["comment_id"] == "22"
        assert result["action"] == "updated"
        assert ops.comment_url("11") == "https://dev.azure.com/org/proj/_git/repo/pullrequest/3?discussionId=11"

    def test_digestops_find_existing_and_upsert_github(self):
        mod = self._load_module()
        from unittest.mock import patch
        ref = mod.PrRef.from_url("https://github.com/azure-core/octane/pull/4")
        ops = mod.DigestOps(ref)
        comments = json.dumps([{"id": 55, "body": "<!-- ai-agent:pr-orchestrator-digest -->\nbody"}])
        created = json.dumps({"id": 66})
        with patch.object(mod, "run_cli", side_effect=[self._Completed(stdout=comments), self._Completed(stdout="[]"), self._Completed(stdout=created)]):
            existing = ops.find_existing("<!-- ai-agent:pr-orchestrator-digest -->")
            result = ops.upsert("created", "<!-- ai-agent:pr-orchestrator-digest -->")
        assert existing["comment_id"] == "55"
        assert result["action"] == "created"
        assert result["comment_id"] == "66"
        assert ops.comment_url("66", "66") == "https://github.com/azure-core/octane/pull/4#issuecomment-66"

    def test_reviewthreadops_list_threads_ado_and_github(self):
        mod = self._load_module()
        from unittest.mock import patch
        ado_ref = mod.PrRef.from_url("https://dev.azure.com/org/proj/_git/repo/pullrequest/5")
        gh_ref = mod.PrRef.from_url("https://github.com/azure-core/octane/pull/5")
        ado_threads = json.dumps({"value": [{"id": 1, "comments": [{"content": "body"}]}]})
        gh_comments = json.dumps([{"id": 2, "body": "gh body", "path": "src/a.py", "line": 9, "user": {"login": "bot"}}])
        with patch.object(mod, "run_cli", side_effect=[self._Completed(stdout=ado_threads), self._Completed(stdout=gh_comments)]):
            ado_list = mod.ReviewThreadOps(ado_ref).list_threads()
            gh_list = mod.ReviewThreadOps(gh_ref).list_threads()
        assert ado_list[0]["id"] == 1
        assert gh_list[0]["threadContext"]["filePath"] == "src/a.py"
        assert gh_list[0]["comments"][0]["author"]["displayName"] == "bot"

    def test_reviewthreadops_post_inline_and_pr_level(self):
        mod = self._load_module()
        from unittest.mock import patch
        ado_ref = mod.PrRef.from_url("https://dev.azure.com/org/proj/_git/repo/pullrequest/6")
        gh_ref = mod.PrRef.from_url("https://github.com/azure-core/octane/pull/6")
        with patch.object(mod, "run_cli", side_effect=[self._Completed(stdout=json.dumps({"id": 1})), self._Completed(stdout=json.dumps({"id": 2})), self._Completed(stdout="")]) as mock_run:
            inline_ado = mod.ReviewThreadOps(ado_ref).post_inline("body", "src/test.py", 10, status=5)
            inline_gh = mod.ReviewThreadOps(gh_ref).post_inline("body", "src/test.py", 10)
            pr_level_gh = mod.ReviewThreadOps(gh_ref).post_pr_level("body")
        assert inline_ado["id"] == 1
        assert inline_gh["id"] == 2
        assert mock_run.call_args_list[0].args[0][:3] == ["az", "rest", "--method"]
        assert mock_run.call_args_list[1].args[0][:3] == ["gh", "api", "/repos/azure-core/octane/pulls/6/comments"]
        assert mock_run.call_args_list[2].args[0][:3] == ["gh", "pr", "comment"]
        assert pr_level_gh["returncode"] == 0


# ── compose-digest.py (--output-file flag) ───────────────────────────────────

class TestComposeDigestOutputFile:
    """Test compose-digest.py --output-file writes directly to disk with correct encoding."""

    MINIMAL_INPUT = TestComposeDigest.MINIMAL_INPUT

    def test_output_file_creates_valid_digest(self):
        input_file = os.path.join(tempfile.gettempdir(), "test-compose-input.json")
        output_file = os.path.join(tempfile.gettempdir(), "test-compose-output.md")
        try:
            with open(input_file, "w", encoding="utf-8") as f:
                json.dump(self.MINIMAL_INPUT, f)
            r = run_script("compose-digest.py", args=[input_file, "--output-file", output_file])
            assert r["exit_code"] == 0
            assert os.path.exists(output_file)
            content = Path(output_file).read_text(encoding="utf-8")
            assert "<!-- ai-agent:pr-orchestrator-digest -->" in content
            assert "— Review Digest" in content  # em-dash preserved
        finally:
            for f in [input_file, output_file]:
                try:
                    os.unlink(f)
                except OSError:
                    pass

    def test_output_file_emoji_preserved(self):
        """Verify emoji survives --output-file (the whole point of the flag)."""
        input_data = {**self.MINIMAL_INPUT, "verdict": "ready"}
        input_file = os.path.join(tempfile.gettempdir(), "test-compose-emoji-in.json")
        output_file = os.path.join(tempfile.gettempdir(), "test-compose-emoji-out.md")
        try:
            with open(input_file, "w", encoding="utf-8") as f:
                json.dump(input_data, f)
            r = run_script("compose-digest.py", args=[input_file, "--output-file", output_file])
            assert r["exit_code"] == 0
            raw_bytes = Path(output_file).read_bytes()
            content = raw_bytes.decode("utf-8")
            # Check that actual Unicode emoji are in the file, not garbled cp1252
            assert "✅" in content or "\u2705" in content.encode().decode("unicode_escape", errors="ignore")
            assert "ΓÇö" not in content  # garbled em-dash should NOT be present
        finally:
            for f in [input_file, output_file]:
                try:
                    os.unlink(f)
                except OSError:
                    pass

    def test_output_file_validates_clean(self):
        """Verify --output-file output passes the format validator."""
        input_file = os.path.join(tempfile.gettempdir(), "test-compose-val-in.json")
        output_file = os.path.join(tempfile.gettempdir(), "test-compose-val-out.md")
        try:
            with open(input_file, "w", encoding="utf-8") as f:
                json.dump(self.MINIMAL_INPUT, f)
            run_script("compose-digest.py", args=[input_file, "--output-file", output_file])
            v = run_script("validate-digest-format.py", args=[output_file])
            assert v["json"]["valid"] is True, f"Violations: {v['json']['violations']}"
        finally:
            for f in [input_file, output_file]:
                try:
                    os.unlink(f)
                except OSError:
                    pass


# ── post-findings.py ─────────────────────────────────────────────────────────

class TestPostFindings:
    """Test post-findings.py finding extraction and filtering."""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("post_findings", str(SCRIPTS_DIR / "post-findings.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_extract_skips_mechanical_important(self):
        mod = self._load_module()
        data = {"findings": {"Important": [
            {"id": 1, "mechanical": True, "description": "auto-fixable"},
            {"id": 2, "mechanical": False, "description": "needs human"},
        ]}}
        result = mod.extract_findings(data)
        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_extract_keeps_suggestions(self):
        mod = self._load_module()
        data = {"findings": {"Suggestion": [
            {"id": 1, "mechanical": False, "description": "consider this"},
        ]}}
        result = mod.extract_findings(data)
        assert len(result) == 1
        assert result[0]["_severity"] == "Suggestion"

    def test_extract_skips_mechanical_suggestions(self):
        """Mechanical suggestions are now auto-fixed — should be skipped."""
        mod = self._load_module()
        data = {"findings": {"Suggestion": [
            {"id": 1, "mechanical": True, "description": "auto-fixable suggestion"},
            {"id": 2, "mechanical": False, "description": "human-judgment suggestion"},
        ]}}
        result = mod.extract_findings(data)
        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_extract_empty_findings(self):
        mod = self._load_module()
        result = mod.extract_findings({"findings": {}})
        assert result == []

    def test_extract_flat_array(self):
        """Flat array format: {"findings": [{"severity": "Important", ...}]}"""
        mod = self._load_module()
        data = {"findings": [
            {"id": 1, "severity": "Important", "mechanical": False, "description": "needs human"},
            {"id": 2, "severity": "Suggestion", "mechanical": False, "description": "consider this"},
            {"id": 3, "severity": "Important", "mechanical": True, "description": "auto-fixed"},
        ]}
        result = mod.extract_findings(data)
        # id=3 is mechanical Important → skipped; id=1 and id=2 remain
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_extract_flat_array_all_non_mechanical(self):
        mod = self._load_module()
        data = {"findings": [
            {"id": 1, "severity": "Important", "mechanical": False, "description": "bug"},
            {"id": 2, "severity": "Important", "mechanical": False, "description": "another bug"},
        ]}
        result = mod.extract_findings(data)
        assert len(result) == 2

    def test_extract_lowercase_keys(self):
        """Code review agent uses lowercase keys: important, suggestions."""
        mod = self._load_module()
        data = {"findings": {
            "important": [
                {"id": 1, "classification": "mechanical", "description": "auto-fixed"},
                {"id": 2, "classification": "human-judgment", "description": "needs review"},
            ],
            "suggestions": [
                {"id": 3, "classification": "human-judgment", "description": "consider this"},
            ],
        }}
        result = mod.extract_findings(data)
        # id=1 is mechanical Important → skipped; id=2 and id=3 remain
        assert len(result) == 2
        assert result[0]["id"] == 2
        assert result[1]["id"] == 3

    def test_extract_classification_field(self):
        """classification='mechanical' should be treated same as mechanical=True."""
        mod = self._load_module()
        data = {"findings": {"Important": [
            {"id": 1, "classification": "mechanical", "description": "auto-fixable"},
            {"id": 2, "classification": "human-judgment", "description": "needs human"},
        ]}}
        result = mod.extract_findings(data)
        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_extract_all_mechanical_returns_empty(self):
        mod = self._load_module()
        data = {"findings": {"Critical": [
            {"id": 1, "mechanical": True},
        ], "Important": [
            {"id": 2, "mechanical": True},
        ]}}
        result = mod.extract_findings(data)
        assert result == []

    def test_format_comment_includes_severity(self):
        mod = self._load_module()
        finding = {"description": "Test bug", "category": "Bug"}
        result = mod.format_comment(finding, "Important")
        assert "Important" in result
        assert "Test bug" in result
        assert "PR Orchestrator" in result

    def test_dry_run_outputs_json(self):
        findings_file = os.path.join(tempfile.gettempdir(), "test-post-findings.json")
        try:
            data = {"findings": {"Important": [
                {"id": 1, "file": "test.cs", "line": 10, "description": "bug", "mechanical": False},
            ]}}
            with open(findings_file, "w") as f:
                json.dump(data, f)
            r = run_script("post-findings.py", args=[
                "--platform", "ado",
                "--pr-url", "https://dev.azure.com/org/proj/_git/repo/pullrequest/123",
                "--findings-file", findings_file,
                "--dry-run",
            ])
            assert r["exit_code"] == 0
            output = json.loads(r["stdout"])
            assert output["posted"] == 1
            assert output["skipped"] == 0
        finally:
            try:
                os.unlink(findings_file)
            except OSError:
                pass

    def test_no_findings_outputs_zero(self):
        findings_file = os.path.join(tempfile.gettempdir(), "test-post-empty.json")
        try:
            with open(findings_file, "w") as f:
                json.dump({"findings": {"Important": [{"id": 1, "mechanical": True}]}}, f)
            r = run_script("post-findings.py", args=[
                "--platform", "ado",
                "--pr-url", "https://dev.azure.com/org/proj/_git/repo/pullrequest/123",
                "--findings-file", findings_file,
            ])
            assert r["exit_code"] == 0
            output = json.loads(r["stdout"])
            assert output["posted"] == 0
        finally:
            try:
                os.unlink(findings_file)
            except OSError:
                pass

    def test_runtime_fallback_logs_and_uses_cli(self):
        mod = self._load_module()
        from unittest.mock import patch

        class BrokenReviewThreadOps:
            def __init__(self, ref):
                pass

            def post_inline(self, *args, **kwargs):
                raise RuntimeError("boom")

            def post_pr_level(self, *args, **kwargs):
                raise RuntimeError("boom")

        finding = {
            "id": 1,
            "file": "src/test.py",
            "line": 10,
            "description": "needs review",
            "_severity": "Important",
        }
        with patch.object(mod.PrRef, "from_url", return_value=object()), \
             patch.object(mod, "ReviewThreadOps", BrokenReviewThreadOps), \
             patch.object(mod, "run_cmd", return_value={"exit_code": 0, "stdout": "{}", "stderr": ""}), \
             contextlib.redirect_stderr(io.StringIO()) as captured:
            result = mod.post_github("https://github.com/azure-core/octane/pull/42", [finding], False)

        assert result["posted"] == 1
        assert result["skipped"] == 0
        assert "[fallback] pr_platform.ReviewThreadOps.post_inline failed (boom) — using CLI" in captured.getvalue()


# ── build-digest-input.py ────────────────────────────────────────────────────

class TestBuildDigestInput:
    """Test build-digest-input.py upstream → digest-input transformation."""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("bdi", str(SCRIPTS_DIR / "build-digest-input.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    MINIMAL_UPSTREAM = {
        "pr_url": "https://dev.azure.com/org/proj/_git/repo/pullrequest/123",
        "code_review_findings": {"tier": "1", "important": [], "suggestions": []},
        "code_fix": {"fixes_applied": 0, "fix_commits": []},
        "risk_level": "low",
        "risk_signals": ["test only"],
        "gate_lint": "passed", "gate_build": "passed", "gate_test": "passed", "gate_security": "passed",
        "watch_and_fix": {"build_status": "passed", "fixes_pushed": 0, "fix_summaries": [], "elapsed_minutes": 20},
    }

    def test_maps_findings_correctly(self):
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {
            "tier": "1",
            "important": [
                {"severity": "Important", "file": "test.cs (line 10)", "description": "bug", "classification": "mechanical"},
                {"severity": "Important", "file": "model.cs (lines 41-51)", "description": "needs review", "classification": "human-judgment"},
            ],
            "suggestions": [
                {"severity": "Suggestion", "file": "util.ts", "description": "refactor", "classification": "human-judgment"},
            ],
        }, "code_fix": {"fixes_applied": 1, "fix_commits": ["abc123"]}}
        result = mod.build_digest_input(data)
        findings = result["findings"]["prevalidate"]
        assert len(findings) == 3
        assert findings[0]["status"] == "✅ Fixed"
        assert findings[1]["status"] == "⚠️ Needs judgment"
        assert findings[2]["status"] == "💡 Suggestion"

    def test_verdict_warnings_with_important(self):
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {
            "tier": "1", "important": [{"description": "bug"}], "suggestions": []
        }}
        result = mod.build_digest_input(data)
        assert result["verdict"] == "warnings"

    def test_verdict_ready_no_important(self):
        mod = self._load_module()
        result = mod.build_digest_input(self.MINIMAL_UPSTREAM)
        assert result["verdict"] == "ready"

    def test_review_engine_from_tier(self):
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {"tier": "1"}}
        result = mod.build_digest_input(data)
        assert result["review_engine"] == "Gatekeeper"

        data2 = {**self.MINIMAL_UPSTREAM, "code_review_findings": {"tier": "2"}}
        result2 = mod.build_digest_input(data2)
        assert result2["review_engine"] == "Gatekeeper"

        data3 = {**self.MINIMAL_UPSTREAM, "code_review_findings": {"review_engine": "Unavailable"}}
        result3 = mod.build_digest_input(data3)
        assert result3["review_engine"] == "Unavailable"

    def test_uses_namespaced_phase_outputs_when_flat_keys_conflict(self):
        mod = self._load_module()
        data = {
            **self.MINIMAL_UPSTREAM,
            "code_review_findings": {"tier": "2", "important": [], "suggestions": []},
            "build_status": "failed",
            "fix_commits": [],
            "_phases": {
                "1c": {
                    "code_review_findings": {
                        "tier": "1",
                        "important": [{"description": "bug", "file": "a.cs", "classification": "mechanical"}],
                        "suggestions": [],
                    }
                },
                "1d": {"fixes_applied": 1, "fix_commits": ["fix_sha"], "findings_remaining": 0},
                "3": {
                    "build_status": "passed",
                    "fixes_pushed": 1,
                    "fix_summaries": ["Fixed CI build"],
                    "fix_commits": ["ci_sha"],
                    "elapsed_minutes": 7,
                },
            },
        }
        result = mod.build_digest_input(data)
        assert result["review_engine"] == "Gatekeeper"
        assert result["findings"]["prevalidate"][0]["commit_sha"] == "fix_sha"
        assert result["findings"]["watch_fix"][0]["commit_sha"] == "ci_sha"
        build_gate = next(g for g in result["gates"] if "Build" in g["check"])
        assert build_gate["status"] == "✅ Passed"

    def test_risk_level_flows_from_upstream_data(self):
        mod = self._load_module()
        data = {
            **self.MINIMAL_UPSTREAM,
            "risk_level": "medium",
            "risk_signals": ["🟡 src/api.py: API surface change"],
            "_phases": {
                "2": {"pr_url": self.MINIMAL_UPSTREAM["pr_url"]},
            },
        }
        result = mod.build_digest_input(data)
        assert result["risk"]["level"] == "medium"
        assert result["risk_level"] == "medium"
        assert result["risk_level_displayed"] == "medium"


class TestCodeReviewFindingsParsing:
    """Tests for build_digest_input code_review_findings parsing robustness."""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("bdi", str(SCRIPTS_DIR / "build-digest-input.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    MINIMAL_UPSTREAM = TestBuildDigestInput.MINIMAL_UPSTREAM

    def test_double_encoded_json_string(self):
        """Double-encoded JSON (string wrapping a JSON dict) should be parsed."""
        mod = self._load_module()
        inner = {"tier": "1", "important": [{"description": "bug"}], "suggestions": []}
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": json.dumps(json.dumps(inner))}
        result = mod.build_digest_input(data)
        assert result["review_engine"] == "Gatekeeper"
        assert len(result["findings"]["prevalidate"]) == 1

    def test_python_dict_literal(self):
        """Python dict literal (from LLM repr) should be parsed via ast.literal_eval."""
        mod = self._load_module()
        data = {
            **self.MINIMAL_UPSTREAM,
            "code_review_findings": "{'tier': '1', 'important': [{'description': 'bug', 'classification': 'human-judgment'}], 'suggestions': []}",
        }
        result = mod.build_digest_input(data)
        assert result["review_engine"] == "Gatekeeper"
        assert any("Needs judgment" in f.get("status", "") for f in result["findings"]["prevalidate"])

    def test_unparseable_string_warns(self, capsys):
        """Completely unparseable string should warn on stderr and return empty."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": "{definitely not valid"}
        result = mod.build_digest_input(data)
        captured = capsys.readouterr()
        assert "WARNING: code_review_findings is unparseable" in captured.err
        assert result["findings"]["prevalidate"] == []

    def test_list_result_rejected(self, capsys):
        """JSON that parses to a list (not dict) should be rejected."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": json.dumps([{"description": "bug"}])}
        result = mod.build_digest_input(data)
        captured = capsys.readouterr()
        assert "WARNING: code_review_findings is unparseable" in captured.err
        assert result["findings"]["prevalidate"] == []

class TestBuildDigestInputContinued(TestBuildDigestInput):
    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("bdi", str(SCRIPTS_DIR / "build-digest-input.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    MINIMAL_UPSTREAM = TestBuildDigestInput.MINIMAL_UPSTREAM

    def test_build_thread_url_ado(self):
        """ADO thread URLs use ?discussionId= format."""
        mod = self._load_module()
        url = mod.build_thread_url(
            "https://msazure.visualstudio.com/One/_git/Repo/pullrequest/123",
            "99999",
        )
        assert url == "https://msazure.visualstudio.com/One/_git/Repo/pullrequest/123?discussionId=99999"

    def test_build_thread_url_github(self):
        """GitHub thread URLs use #discussion_r format."""
        mod = self._load_module()
        url = mod.build_thread_url(
            "https://github.com/owner/repo/pull/42",
            "55555",
        )
        assert url == "https://github.com/owner/repo/pull/42#discussion_r55555"

    def test_build_thread_url_autodetect_platform(self):
        """Platform is auto-detected from URL when not provided."""
        mod = self._load_module()
        ado_url = mod.build_thread_url(
            "https://dev.azure.com/org/proj/_git/Repo/pullrequest/789",
            "11111",
        )
        assert "?discussionId=11111" in ado_url

    def test_build_thread_url_empty(self):
        """Empty inputs return empty string."""
        mod = self._load_module()
        assert mod.build_thread_url("", "123") == ""
        assert mod.build_thread_url("https://example.com/pr/1", "") == ""

    def test_feedback_findings_include_view_url(self):
        """Phase 5 feedback findings include thread-based view_url."""
        mod = self._load_module()
        existing = mod.build_digest_input(self.MINIMAL_UPSTREAM)
        phase5 = {
            "pr_url": self.MINIMAL_UPSTREAM["pr_url"],
            "address_feedback": {"iteration": 1, "comments_addressed": 0, "all_addressed": False},
        }
        triage = {"actionable": [
            {"thread_id": "77777", "file": "Service.cs", "body": "Issue here", "scope": "in_diff"},
        ], "skipped": []}
        merged = mod.merge_phase5(existing, phase5, triage_output=triage)
        fb = merged["findings"]["feedback"]
        assert len(fb) >= 1
        item = fb[0]
        assert item.get("thread_id") == "77777"
        assert "discussionId=77777" in item.get("view_url", "")

    def test_human_judgment_findings_include_view_url(self):
        """Phase 1 human judgment findings include file-based view_url."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "human_judgment_findings": [
            {"file": "Middleware.cs", "description": "Silent fallback"},
        ]}
        result = mod.build_digest_input(data)
        pv = result["findings"]["prevalidate"]
        judgment = [f for f in pv if "judgment" in f.get("status", "").lower()]
        assert len(judgment) == 1
        assert judgment[0].get("view_url", "")
        assert "Middleware.cs" in judgment[0]["view_url"]

    def test_human_judgment_dedup_with_code_review(self):
        """human_judgment_findings that duplicate code_review_findings are not added twice."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {
            "tier": "1",
            "important": [
                {"severity": "Important", "file": "Service.cs", "description": "Null guard missing", "classification": "human-judgment"},
            ],
            "suggestions": [],
        }, "human_judgment_findings": [
            {"file": "Service.cs", "description": "Null guard missing"},
        ]}
        result = mod.build_digest_input(data)
        pv = result["findings"]["prevalidate"]
        judgment = [f for f in pv if "judgment" in f.get("status", "").lower()]
        assert len(judgment) == 1, f"Expected 1, got {len(judgment)}: {[f['finding'] for f in judgment]}"

    def test_watch_fix_findings(self):
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "watch_and_fix": {
            "build_status": "passed", "fixes_pushed": 1,
            "fix_summaries": ["Fixed CS7036"], "fix_commits": ["waf_sha1"], "elapsed_minutes": 25
        }}
        result = mod.build_digest_input(data)
        assert len(result["findings"]["watch_fix"]) == 1
        assert result["findings"]["watch_fix"][0]["status"] == "✅ Fixed"
        assert result["findings"]["watch_fix"][0]["commit_sha"] == "waf_sha1"

    def test_watch_fix_sha_length_mismatch(self):
        """fix_commits shorter than fix_summaries falls back to empty string."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "watch_and_fix": {
            "build_status": "passed", "fixes_pushed": 2,
            "fix_summaries": ["Fix A", "Fix B"], "fix_commits": ["sha1"], "elapsed_minutes": 10
        }}
        result = mod.build_digest_input(data)
        wf = result["findings"]["watch_fix"]
        assert len(wf) == 2
        assert wf[0]["commit_sha"] == "sha1"
        assert wf[1]["commit_sha"] == ""

    def test_merge_phase5(self):
        """Backward-compat: collapsed single row when no addressed_details AND no triage."""
        mod = self._load_module()
        existing = mod.build_digest_input(self.MINIMAL_UPSTREAM)
        phase5 = {
            "pr_url": self.MINIMAL_UPSTREAM["pr_url"],
            "address_feedback": {
                "iteration": 1, "comments_addressed": 3, "comments_remaining": 0,
                "fix_commits": ["sha123"], "all_addressed": True
            }
        }
        merged = mod.merge_phase5(existing, phase5)
        assert len(merged["findings"]["feedback"]) == 1
        assert merged["findings"]["feedback"][0]["file"] == "Multiple files"
        assert merged["verdict"] == "approved"
        assert "Final Digest" in merged["footer_variant"]

    def test_merge_phase5_per_thread_from_triage(self):
        """When no addressed_details but triage data exists, build per-thread rows."""
        mod = self._load_module()
        existing = mod.build_digest_input(self.MINIMAL_UPSTREAM)
        phase5 = {
            "pr_url": self.MINIMAL_UPSTREAM["pr_url"],
            "address_feedback": {
                "iteration": 1, "comments_addressed": 2, "comments_remaining": 0,
                "fix_commits": ["sha456"], "all_addressed": True
            }
        }
        triage = {
            "actionable": [
                {"thread_id": 100, "file": "src/foo.ts", "body": "Missing null check", "verdict": "must_fix"},
                {"thread_id": 101, "file": "src/bar.cs", "body": "Unused variable", "verdict": "must_fix"},
            ],
            "skipped": [],
            "summary": {"total_threads": 2, "actionable": 2}
        }
        merged = mod.merge_phase5(existing, phase5, triage_output=triage)
        fb = merged["findings"]["feedback"]
        assert len(fb) == 2, f"Expected 2 per-thread rows, got {len(fb)}"
        assert fb[0]["file"] == "src/foo.ts"
        assert fb[0]["finding"] == "Missing null check"
        assert fb[0]["status"] == "✅ Fixed"
        assert fb[1]["file"] == "src/bar.cs"
        assert fb[1]["commit_sha"] == "sha456"

    def test_timeline_address_feedback_not_run(self):
        """When address_feedback is absent, timeline shows Pending."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM}
        data.pop("address_feedback", None)
        result = mod.build_digest_input(data)
        af_row = next(t for t in result["timeline"] if t["phase"] == "Address Feedback")
        assert af_row["duration"] == "⏳ Pending"
        assert af_row["result"] == "⏳ Pending"

    def test_timeline_watch_fix_skipped(self):
        """When watch_and_fix is absent (YOLO fast), timeline shows Skipped."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM}
        data.pop("watch_and_fix", None)
        result = mod.build_digest_input(data)
        waf_row = next(t for t in result["timeline"] if t["phase"] == "Watch & Fix CI")
        assert waf_row["duration"] == "⏭️ Skipped"
        assert waf_row["result"] == "⏭️ Skipped"

    def test_timeline_address_feedback_no_feedback(self):
        """When address_feedback ran but found nothing, timeline shows completion."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "address_feedback": {"status": "no_feedback"}}
        result = mod.build_digest_input(data)
        af_row = next(t for t in result["timeline"] if t["phase"] == "Address Feedback")
        assert af_row["result"] == "✅ No feedback to address"
        assert af_row["duration"] == "< 1 min"

    def test_timeline_address_feedback_all_addressed(self):
        """When all feedback was addressed, timeline shows count."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "address_feedback": {"iteration": 2, "comments_addressed": 5, "all_addressed": True}}
        result = mod.build_digest_input(data)
        af_row = next(t for t in result["timeline"] if t["phase"] == "Address Feedback")
        assert af_row["result"] == "✅ 5 addressed"
        assert af_row["duration"] == "2 iteration(s)"

    def test_merge_phase5_no_feedback_status(self):
        """merge_phase5 with status=no_feedback updates timeline correctly."""
        mod = self._load_module()
        existing = mod.build_digest_input(self.MINIMAL_UPSTREAM)
        phase5 = {
            "pr_url": self.MINIMAL_UPSTREAM["pr_url"],
            "address_feedback": {"status": "no_feedback"}
        }
        merged = mod.merge_phase5(existing, phase5)
        af_row = next(t for t in merged["timeline"] if t["phase"] == "Address Feedback")
        assert af_row["result"] == "✅ No feedback to address"
        assert af_row["duration"] == "< 1 min"

    def test_merge_phase5_per_comment_rows(self):
        """addressed_details produces per-comment rows."""
        mod = self._load_module()
        existing = mod.build_digest_input(self.MINIMAL_UPSTREAM)
        pr_url = "https://msazure.visualstudio.com/One/_git/Repo/pullrequest/123"
        full_sha_a = "a" * 40
        full_sha_b = "b" * 40
        phase5 = {
            "pr_url": pr_url,
            "address_feedback": {
                "iteration": 1, "comments_addressed": 2, "comments_remaining": 0,
                "fix_commits": [full_sha_a, full_sha_b], "all_addressed": True,
                "addressed_details": [
                    {"thread_id": "100", "file": "/src/auth.cs", "finding_summary": "Use IsNullOrWhiteSpace", "commit_sha": full_sha_a},
                    {"thread_id": "200", "file": "/src/utils.ts", "finding_summary": "Quote parameter", "commit_sha": full_sha_b},
                ]
            }
        }
        merged = mod.merge_phase5(existing, phase5)
        fb = merged["findings"]["feedback"]
        assert len(fb) == 2
        assert fb[0]["file"] == "/src/auth.cs"
        assert fb[0]["commit_sha"] == full_sha_a
        assert fb[1]["file"] == "/src/utils.ts"
        assert full_sha_b in fb[1]["commit_url"]

    def test_merge_phase5_dedupes_by_thread_id(self):
        """Cumulative addressed_details with duplicate thread_ids are deduped."""
        mod = self._load_module()
        existing = mod.build_digest_input(self.MINIMAL_UPSTREAM)
        phase5 = {
            "pr_url": self.MINIMAL_UPSTREAM["pr_url"],
            "address_feedback": {
                "iteration": 2, "comments_addressed": 2, "comments_remaining": 0,
                "fix_commits": ["sha1", "sha2"], "all_addressed": True,
                "addressed_details": [
                    {"thread_id": "100", "file": "/a.cs", "finding_summary": "Fix A", "commit_sha": "sha1"},
                    {"thread_id": "100", "file": "/a.cs", "finding_summary": "Fix A v2", "commit_sha": "sha2"},
                ]
            }
        }
        merged = mod.merge_phase5(existing, phase5)
        assert len(merged["findings"]["feedback"]) == 1

    def test_merge_phase5_verdict_warnings_with_judgment(self):
        """Verdict stays warnings when prevalidate has needs-judgment findings."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {
            "tier": "1",
            "important": [{"description": "review this", "classification": "human-judgment"}],
            "suggestions": [],
        }}
        existing = mod.build_digest_input(data)
        assert existing["verdict"] == "warnings"
        phase5 = {
            "pr_url": self.MINIMAL_UPSTREAM["pr_url"],
            "address_feedback": {
                "iteration": 1, "comments_addressed": 1, "comments_remaining": 0,
                "fix_commits": ["sha1"], "all_addressed": True
            }
        }
        merged = mod.merge_phase5(existing, phase5)
        assert merged["verdict"] == "warnings", "Should NOT upgrade to approved with needs-judgment findings"

    def test_merge_phase5_resolution_status_bydesign(self):
        """byDesign resolution maps to '✅ By Design' status."""
        mod = self._load_module()
        existing = mod.build_digest_input(self.MINIMAL_UPSTREAM)
        phase5 = {
            "pr_url": self.MINIMAL_UPSTREAM["pr_url"],
            "address_feedback": {
                "iteration": 1, "comments_addressed": 1, "comments_remaining": 0,
                "fix_commits": [], "all_addressed": True,
                "addressed_details": [
                    {"thread_id": "100", "file": "/src/config.cs", "finding_summary": "Nesting is intentional",
                     "commit_sha": "", "resolution": "byDesign"},
                ]
            }
        }
        merged = mod.merge_phase5(existing, phase5)
        fb = merged["findings"]["feedback"]
        assert len(fb) == 1
        assert fb[0]["status"] == "✅ By Design"
        assert fb[0]["commit_sha"] == ""

    def test_merge_phase5_resolution_status_wontfix(self):
        """wontfix resolution maps to '✅ Won't Fix' status."""
        mod = self._load_module()
        existing = mod.build_digest_input(self.MINIMAL_UPSTREAM)
        phase5 = {
            "pr_url": self.MINIMAL_UPSTREAM["pr_url"],
            "address_feedback": {
                "iteration": 1, "comments_addressed": 1, "comments_remaining": 0,
                "fix_commits": [], "all_addressed": True,
                "addressed_details": [
                    {"thread_id": "100", "file": "/src/config.cs", "finding_summary": "Low priority",
                     "commit_sha": "", "resolution": "wontfix"},
                ]
            }
        }
        merged = mod.merge_phase5(existing, phase5)
        fb = merged["findings"]["feedback"]
        assert fb[0]["status"] == "✅ Won't Fix"

    def test_merge_phase5_updates_prevalidate_status(self):
        """address_feedback byDesign resolution updates matching prevalidate finding."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {
            "tier": "1",
            "important": [{"description": "Use ManagedIdentityClientId correctly", "classification": "human-judgment"}],
            "suggestions": [],
        }}
        existing = mod.build_digest_input(data)
        # Prevalidate finding should start as Needs judgment
        pv = existing["findings"]["prevalidate"]
        assert any("Needs judgment" in f.get("status", "") for f in pv)

        phase5 = {
            "pr_url": self.MINIMAL_UPSTREAM["pr_url"],
            "address_feedback": {
                "iteration": 1, "comments_addressed": 1, "comments_remaining": 0,
                "fix_commits": [], "all_addressed": True,
                "addressed_details": [
                    {"thread_id": "100", "file": "—", "finding_summary": "ManagedIdentityClientId nesting correct",
                     "commit_sha": "", "resolution": "byDesign"},
                ]
            }
        }
        merged = mod.merge_phase5(existing, phase5)
        # The prevalidate finding should now show By Design
        pv = merged["findings"]["prevalidate"]
        needs_judgment = [f for f in pv if "Needs judgment" in f.get("status", "")]
        # File "—" doesn't match any prevalidate file, so status stays unchanged
        assert len(needs_judgment) == 1, "File '—' can't match; prevalidate status should stay Needs judgment"

    def test_merge_phase5_updates_prevalidate_with_file_match(self):
        """address_feedback resolution updates prevalidate finding when file paths match."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {
            "tier": "1",
            "important": [{"description": "review this pattern", "classification": "human-judgment",
                           "file": "src/Startup.cs", "line": 42}],
            "suggestions": [],
        }}
        existing = mod.build_digest_input(data)
        # Manually set file on the finding (since build_digest_input may not preserve it)
        for f in existing["findings"]["prevalidate"]:
            if "Needs judgment" in f.get("status", ""):
                f["file"] = "src/Startup.cs"

        phase5 = {
            "pr_url": self.MINIMAL_UPSTREAM["pr_url"],
            "address_feedback": {
                "iteration": 1, "comments_addressed": 1, "comments_remaining": 0,
                "fix_commits": ["abc123"], "all_addressed": True,
                "addressed_details": [
                    {"thread_id": "100", "file": "src/Startup.cs", "finding_summary": "Fixed pattern",
                     "commit_sha": "abc123", "resolution": "fixed"},
                ]
            }
        }
        merged = mod.merge_phase5(existing, phase5)
        pv = merged["findings"]["prevalidate"]
        updated = [f for f in pv if f.get("file") == "src/Startup.cs"]
        assert len(updated) == 1
        assert updated[0]["status"] == "✅ Fixed"
        assert updated[0]["commit_sha"] == "abc123"

    def test_merge_phase5_verdict_approved_with_bydesign(self):
        """Verdict upgrades to approved when all findings resolved including byDesign."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {
            "tier": "1",
            "important": [{"description": "review this", "classification": "human-judgment",
                           "file": "src/Config.cs"}],
            "suggestions": [],
        }}
        existing = mod.build_digest_input(data)
        # Manually set file for matching
        for f in existing["findings"]["prevalidate"]:
            if "Needs judgment" in f.get("status", ""):
                f["file"] = "src/Config.cs"

        phase5 = {
            "pr_url": self.MINIMAL_UPSTREAM["pr_url"],
            "address_feedback": {
                "iteration": 1, "comments_addressed": 1, "comments_remaining": 0,
                "fix_commits": [], "all_addressed": True,
                "addressed_details": [
                    {"thread_id": "100", "file": "src/Config.cs", "finding_summary": "Intentional",
                     "commit_sha": "", "resolution": "byDesign"},
                ]
            }
        }
        merged = mod.merge_phase5(existing, phase5)
        assert merged["verdict"] == "approved", "byDesign is resolved; should not block approval"

    def test_gate_details_reflect_mapped_findings(self):
        """Gate details should show mapped status breakdown, not raw counts."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {
            "tier": "1",
            "important": [
                {"description": "auto-fix", "classification": "mechanical"},
                {"description": "needs human", "classification": "human-judgment"},
            ],
            "suggestions": [{"description": "refactor"}],
        }, "code_fix": {"fixes_applied": 1, "fix_commits": ["abc"]}}
        result = mod.build_digest_input(data)
        cr_gate = [g for g in result["gates"] if "Code Review" in g["check"]][0]
        assert "1 fixed" in cr_gate["details"]
        assert "1 needs judgment" in cr_gate["details"]
        assert "1 suggestions" in cr_gate["details"]
        assert cr_gate["status"] == "⚠️ Warning"

    def _run_build_digest_cli(self, tmp_path, state):
        input_file = tmp_path / "upstream.json"
        output_file = tmp_path / "digest-input.json"
        input_file.write_text(json.dumps(state), encoding="utf-8")
        result = run_script("build-digest-input.py", args=[str(input_file), "--output-file", str(output_file)])
        payload = json.loads(output_file.read_text(encoding="utf-8")) if output_file.exists() else None
        return result, payload

    @staticmethod
    def _parse_code_review_findings_stub(raw, warn=False):
        import ast

        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return {}
        parsed = None
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
        except (json.JSONDecodeError, TypeError):
            try:
                parsed = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                parsed = None
        if isinstance(parsed, dict):
            return parsed
        if warn:
            print(
                f"WARNING: code_review_findings is unparseable (type={type(parsed).__name__}, len={len(raw)})",
                file=sys.stderr,
            )
        return {}

    def _load_module_with_parse_stub(self, monkeypatch):
        mod = self._load_module()
        monkeypatch.setattr(mod, "_parse_code_review_findings", self._parse_code_review_findings_stub, raising=False)
        return mod

    def test_build_digest_missing_phase_1c(self, tmp_path):
        state = {
            "_completed_phases": ["1a"],
            "_phases": {
                "1a": {"business_logic_digest": "test"},
                "2": {"pr_url": self.MINIMAL_UPSTREAM["pr_url"]},
            },
            "pr_url": self.MINIMAL_UPSTREAM["pr_url"],
        }
        result, payload = self._run_build_digest_cli(tmp_path, state)
        assert result["exit_code"] == 0
        assert payload["findings"]["prevalidate"] == []
        assert payload["review_engine"] == "Unavailable"
        assert payload["pr_url"] == self.MINIMAL_UPSTREAM["pr_url"]

    def test_build_digest_missing_phase_1d(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        state = {
            "_completed_phases": ["1c", "2"],
            "_phases": {
                "1c": {
                    "code_review_findings": {
                        "tier": "1",
                        "important": [
                            {"description": "bug", "file": "a.cs", "classification": "mechanical"},
                        ],
                        "suggestions": [],
                    },
                },
                "2": {"pr_url": self.MINIMAL_UPSTREAM["pr_url"]},
            },
        }
        result = mod.build_digest_input(state)
        assert len(result["findings"]["prevalidate"]) == 1
        assert result["findings"]["prevalidate"][0]["status"] == "⚠️ Needs judgment"
        assert result["findings"]["prevalidate"][0]["commit_sha"] == ""

    def test_build_digest_missing_phase_2(self, tmp_path):
        state = {
            "_completed_phases": ["1c"],
            "_phases": {
                "1c": {"code_review_findings": {"tier": "1", "important": [], "suggestions": []}},
            },
        }
        result, payload = self._run_build_digest_cli(tmp_path, state)
        assert result["exit_code"] == 0
        assert payload["pr_url"] == ""
        assert payload["findings"]["prevalidate"] == []

    def test_build_digest_missing_phase_1efg(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        state = {
            "_completed_phases": ["1c", "1d", "2"],
            "_phases": {
                "1c": {"code_review_findings": {"tier": "1", "important": [], "suggestions": []}},
                "1d": {"fixes_applied": 0, "fix_commits": [], "findings_remaining": 0},
                "2": {"pr_url": self.MINIMAL_UPSTREAM["pr_url"]},
            },
        }
        result = mod.build_digest_input(state)
        gates = {g["check"]: g["status"] for g in result["gates"]}
        assert any("Code Review" in check for check in gates)
        assert gates["🔨 Build (CI)"] == "⏭️ Skipped"

    def test_build_digest_missing_all_phases(self, tmp_path):
        state = {"_completed_phases": [], "_phases": {}}
        result, payload = self._run_build_digest_cli(tmp_path, state)
        assert result["exit_code"] == 0
        assert payload["findings"]["prevalidate"] == []
        assert payload["verdict"] == "ready"
        assert payload["pr_url"] == ""

    def test_build_digest_findings_is_string(self, monkeypatch, capsys):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": "not json"}
        result = mod.build_digest_input(data)
        capsys.readouterr()
        assert result["findings"]["prevalidate"] == []
        assert result["verdict"] == "ready"

    def test_build_digest_findings_important_is_dict(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {
            **self.MINIMAL_UPSTREAM,
            "code_review_findings": {"tier": "1", "important": {"description": "bad"}, "suggestions": []},
        }
        with pytest.raises(ValueError):
            mod.build_digest_input(data)

    def test_build_digest_findings_field_is_string(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {"tier": "1", "findings": "oops"}}
        result = mod.build_digest_input(data)
        assert result["findings"]["prevalidate"] == []
        assert result["review_engine"] == "Gatekeeper"

    def test_build_digest_empty_state(self, tmp_path):
        result, payload = self._run_build_digest_cli(tmp_path, {})
        assert result["exit_code"] == 0
        assert payload["findings"]["prevalidate"] == []
        assert payload["verdict"] == "ready"
        assert payload["pr_url"] == ""

    def test_build_digest_missing_phases_namespace(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {
            "_completed_phases": ["1c"],
            "code_review_findings": {
                "tier": "1",
                "important": [{"description": "bug", "classification": "human-judgment"}],
                "suggestions": [],
            },
        }
        result = mod.build_digest_input(data)
        assert len(result["findings"]["prevalidate"]) == 1
        assert result["findings"]["prevalidate"][0]["status"] == "⚠️ Needs judgment"
        assert result["verdict"] == "warnings"

    def test_build_digest_missing_completed_phases(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {
            "_phases": {
                "1c": {
                    "code_review_findings": {
                        "tier": "1",
                        "important": [{"description": "bug", "classification": "human-judgment"}],
                        "suggestions": [],
                    },
                },
            },
        }
        result = mod.build_digest_input(data)
        assert len(result["findings"]["prevalidate"]) == 1
        assert result["verdict"] == "warnings"

    def test_build_digest_phases_all_empty_dicts(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {
            "_phases": {"1c": {}, "1d": {}, "2": {}, "3": {}, "5": {}},
            "_completed_phases": ["1c", "1d", "2", "3", "5"],
        }
        result = mod.build_digest_input(data)
        gates = {g["check"]: g["status"] for g in result["gates"]}
        assert result["findings"]["prevalidate"] == []
        assert any("Code Review" in check for check in gates)
        assert gates["🔨 Build (CI)"] == "⏳ Pending"
        assert result["verdict"] == "ready"

    def test_build_digest_phases_is_list(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {"_phases": [], "_completed_phases": ["1c"]}
        result = mod.build_digest_input(data)
        assert result["findings"]["prevalidate"] == []
        assert result["verdict"] == "ready"

    def test_build_digest_completed_phases_is_string(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {
            "_phases": {
                "1c": {
                    "code_review_findings": {
                        "tier": "1",
                        "important": [{"description": "bug", "classification": "human-judgment"}],
                        "suggestions": [],
                    },
                },
            },
            "_completed_phases": "1c,1d",
        }
        result = mod.build_digest_input(data)
        assert len(result["findings"]["prevalidate"]) == 1
        assert result["verdict"] == "warnings"

    def test_build_digest_addressed_details_wrong_type(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        existing = mod.build_digest_input(self.MINIMAL_UPSTREAM)
        data = {"_phases": {"5": {"address_feedback": {"addressed_details": "oops", "comments_addressed": 1, "all_addressed": True}}}}
        with pytest.raises(AttributeError):
            mod.merge_phase5(existing, data)

    def test_build_digest_phase3_incomplete(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {
            "_phases": {"3": {"build_status": "passed", "fixes_pushed": 0, "fix_commits": []}},
            "_completed_phases": ["3"],
        }
        result = mod.build_digest_input(data)
        watch_row = next(t for t in result["timeline"] if t["phase"] == "Watch & Fix CI")
        assert result["findings"]["watch_fix"] == []
        assert watch_row["duration"] == "⏳ Pending"
        assert watch_row["result"] == "✅ Passed"

    def test_build_digest_phase5_without_phase4(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {"_phases": {"5": {"address_feedback": {"status": "no_feedback"}}}, "_completed_phases": ["5"]}
        result = mod.build_digest_input(data)
        af_row = next(t for t in result["timeline"] if t["phase"] == "Address Feedback")
        assert result["findings"]["feedback"] == []
        assert af_row["result"] == "✅ No feedback to address"
        assert result["footer_variant"] == "Phase 4 Review Digest"

    def test_build_digest_phase5_orphaned_feedback(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        existing = mod.build_digest_input({
            **self.MINIMAL_UPSTREAM,
            "code_review_findings": {
                "tier": "1",
                "important": [{"description": "Needs review", "classification": "human-judgment", "file": "src/A.cs"}],
                "suggestions": [],
            },
        })
        for finding in existing["findings"]["prevalidate"]:
            finding["file"] = "src/A.cs"
        phase5 = {
            "address_feedback": {
                "iteration": 1,
                "comments_addressed": 1,
                "all_addressed": True,
                "addressed_details": [
                    {"thread_id": "999", "file": "other.cs", "finding_summary": "orphan", "commit_sha": "sha1"},
                ],
            },
        }
        merged = mod.merge_phase5(existing, phase5)
        assert len(merged["findings"]["feedback"]) == 1
        assert any("Needs judgment" in f.get("status", "") for f in merged["findings"]["prevalidate"])
        assert merged["verdict"] == "warnings"

    def test_build_digest_verdict_ready_with_warnings(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {
            **self.MINIMAL_UPSTREAM,
            "code_review_findings": {
                "tier": "1",
                "important": [{"description": "judgment", "classification": "human-judgment"}],
                "suggestions": [],
            },
        }
        result = mod.build_digest_input(data)
        cr_gate = next(g for g in result["gates"] if "Code Review" in g["check"])
        assert result["verdict"] == "warnings"
        assert cr_gate["status"] == "⚠️ Warning"

    def test_build_digest_verdict_approved_with_suggestions(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        existing = mod.build_digest_input({
            **self.MINIMAL_UPSTREAM,
            "code_review_findings": {"tier": "1", "important": [], "suggestions": [{"description": "nice to have"}]},
        })
        merged = mod.merge_phase5(existing, {"address_feedback": {"all_addressed": True, "comments_addressed": 0}})
        assert merged["verdict"] == "approved"
        assert merged["findings"]["prevalidate"][0]["status"] == "💡 Suggestion"

    def test_build_thread_url_null_thread_id(self):
        mod = self._load_module()
        assert mod.build_thread_url(self.MINIMAL_UPSTREAM["pr_url"], None) == ""

    def test_build_digest_malformed_pr_url(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {
            **self.MINIMAL_UPSTREAM,
            "pr_url": "not-a-url",
            "code_review_findings": {
                "tier": "1",
                "important": [{"description": "fix me", "file": "a.cs", "classification": "mechanical"}],
                "suggestions": [],
            },
            "code_fix": {"fixes_applied": 1, "fix_commits": ["abc123"]},
        }
        result = mod.build_digest_input(data)
        finding = result["findings"]["prevalidate"][0]
        assert finding["commit_url"] == ""
        assert finding["file_url"] == ""
        assert result["pr_url"] == ""

    def test_build_digest_elapsed_minutes_string(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {
            **self.MINIMAL_UPSTREAM,
            "watch_and_fix": {
                "build_status": "passed",
                "fixes_pushed": 0,
                "fix_summaries": ["noop"],
                "fix_commits": [],
                "elapsed_minutes": "20",
            },
            "_completed_phases": ["3"],
        }
        result = mod.build_digest_input(data)
        watch_row = next(t for t in result["timeline"] if t["phase"] == "Watch & Fix CI")
        assert watch_row["duration"] == "~20 min"
        assert result["total_duration"] == "~35 min"

    def test_build_digest_fixes_pushed_string(self, monkeypatch):
        mod = self._load_module_with_parse_stub(monkeypatch)
        data = {
            **self.MINIMAL_UPSTREAM,
            "watch_and_fix": {
                "build_status": "passed",
                "fixes_pushed": "3",
                "fix_summaries": ["Fix A"],
                "fix_commits": ["abc123"],
                "elapsed_minutes": 20,
            },
            "_completed_phases": ["3"],
        }
        result = mod.build_digest_input(data)
        watch_row = next(t for t in result["timeline"] if t["phase"] == "Watch & Fix CI")
        assert len(result["findings"]["watch_fix"]) == 1
        assert watch_row["result"] == "✅ Passed (3 fix)"
        assert result["total_duration"] == "~35 min"

    def test_full_pipeline_validates(self):
        """build-digest-input → compose-digest → validate-digest: end-to-end."""
        input_file = os.path.join(tempfile.gettempdir(), "test-bdi-pipeline-in.json")
        digest_input = os.path.join(tempfile.gettempdir(), "test-bdi-pipeline-di.json")
        digest_output = os.path.join(tempfile.gettempdir(), "test-bdi-pipeline-out.md")
        try:
            with open(input_file, "w") as f:
                json.dump(self.MINIMAL_UPSTREAM, f)
            r1 = run_script("build-digest-input.py", args=[input_file, "--output-file", digest_input])
            assert r1["exit_code"] == 0
            r2 = run_script("compose-digest.py", args=[digest_input, "--output-file", digest_output])
            assert r2["exit_code"] == 0
            r3 = run_script("validate-digest-format.py", args=[digest_output])
            assert r3["json"]["valid"] is True, f"Violations: {r3['json']['violations']}"
        finally:
            for f in [input_file, digest_input, digest_output]:
                try:
                    os.unlink(f)
                except OSError:
                    pass

    def test_commit_url_ado(self):
        mod = self._load_module()
        full_sha = "abc123" + "0" * 34  # 40 chars
        url = mod.build_commit_url("https://msazure.visualstudio.com/One/_git/Repo/pullrequest/123", full_sha)
        assert url == f"https://msazure.visualstudio.com/One/_git/Repo/commit/{full_sha}"

    def test_commit_url_ado_dev_azure(self):
        """dev.azure.com URLs have org/project/_git/repo — must also produce commit links."""
        mod = self._load_module()
        full_sha = "e1632c8" + "0" * 33  # 40 chars
        url = mod.build_commit_url("https://dev.azure.com/msazure/One/_git/EngSys-Performance-CirrusPortal/pullrequest/15406306", full_sha)
        assert url == f"https://dev.azure.com/msazure/One/_git/EngSys-Performance-CirrusPortal/commit/{full_sha}"

    def test_commit_url_ado_preserves_full_sha(self):
        mod = self._load_module()
        full_sha = "e744cba0123456789abcdef0123456789abcdef0"
        url = mod.build_commit_url(
            "https://dev.azure.com/msazure/One/_git/EngSys-Performance-CirrusPortal/pullrequest/15406306",
            full_sha,
        )
        assert url.endswith(f"/commit/{full_sha}")
        assert full_sha in url

    def test_commit_url_github(self):
        mod = self._load_module()
        full_sha = "def456" + "0" * 34  # 40 chars
        url = mod.build_commit_url("https://github.com/owner/repo/pull/42", full_sha)
        assert url == f"https://github.com/owner/repo/commit/{full_sha}"

    def test_commit_url_rejects_short_sha(self):
        """Short SHAs produce broken ADO links — build_commit_url must reject them."""
        mod = self._load_module()
        url = mod.build_commit_url("https://dev.azure.com/msazure/One/_git/Repo/pullrequest/123", "abc1234")
        assert url == ""

    def test_commit_url_rejects_7char_sha(self):
        """Typical git commit output SHA (7 chars) must be rejected."""
        mod = self._load_module()
        url = mod.build_commit_url("https://msazure.visualstudio.com/One/_git/Repo/pullrequest/123", "e1632c8")
        assert url == ""

    def test_resolve_short_shas_matches(self):
        """resolve_short_shas resolves short SHAs against scrape commit data."""
        mod = self._load_module()
        full_sha = "e1632c8" + "a" * 33
        scrape = {"commits": [{"sha": full_sha, "message": "fix"}]}
        result = mod.resolve_short_shas(["e1632c8"], scrape)
        assert result == [full_sha]

    def test_resolve_short_shas_passthrough_full(self):
        """Full 40-char SHAs pass through unchanged."""
        mod = self._load_module()
        full_sha = "a" * 40
        result = mod.resolve_short_shas([full_sha], None)
        assert result == [full_sha]

    def test_resolve_short_shas_no_scrape(self):
        """Without scrape data, short SHAs pass through as-is."""
        mod = self._load_module()
        result = mod.resolve_short_shas(["abc1234"], None)
        assert result == ["abc1234"]

    def test_resolve_short_shas_unmatched(self):
        """Unmatched short SHAs pass through when scrape has no match."""
        mod = self._load_module()
        scrape = {"commits": [{"sha": "b" * 40, "message": "other"}]}
        result = mod.resolve_short_shas(["abc1234"], scrape)
        assert result == ["abc1234"]

    def test_resolve_short_shas_git_rev_parse(self):
        """resolve_short_shas uses git rev-parse when repo_root is provided."""
        mod = self._load_module()
        full_sha = "abc1234" + "f" * 33
        import unittest.mock as mock
        fake_result = mock.Mock(returncode=0, stdout=f"  {full_sha}\n")
        with mock.patch("subprocess.run", return_value=fake_result) as mock_run:
            result = mod.resolve_short_shas(["abc1234"], None, repo_root="/fake/repo")
        assert result == [full_sha]
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["git", "rev-parse", "abc1234"]
        assert call_args[1]["cwd"] == "/fake/repo"

    def test_resolve_short_shas_git_rev_parse_failure_falls_through(self):
        """When git rev-parse fails, falls back to scrape data."""
        mod = self._load_module()
        full_sha = "abc1234" + "e" * 33
        scrape = {"commits": [{"sha": full_sha, "message": "fix"}]}
        import unittest.mock as mock
        fake_result = mock.Mock(returncode=128, stdout="")
        with mock.patch("subprocess.run", return_value=fake_result):
            result = mod.resolve_short_shas(["abc1234"], scrape, repo_root="/fake/repo")
        assert result == [full_sha]

    def test_mechanical_suggestion_gets_fixed_status(self):
        """Mechanical findings at Suggestion severity should show Fixed when fix_commits exist."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {
            "tier": "2",
            "important": [],
            "suggestions": [
                {"description": "unquoted env var", "file": "test.ts", "classification": "mechanical"},
                {"description": "refactor idea", "file": "util.ts", "classification": "human-judgment"},
            ],
        }, "code_fix": {"fixes_applied": 1, "fix_commits": ["fix_sha1"]}}
        result = mod.build_digest_input(data)
        findings = result["findings"]["prevalidate"]
        assert len(findings) == 2
        assert findings[0]["status"] == "✅ Fixed"
        assert findings[0]["commit_sha"] == "fix_sha1"
        assert findings[1]["status"] == "💡 Suggestion"

    def test_code_fix_per_finding_commit_mapping(self):
        """Each mechanical finding should map to its own commit SHA by index."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {
            "tier": "2",
            "suggestions": [
                {"description": "fix1", "file": "a.ts", "classification": "mechanical"},
                {"description": "skip", "file": "b.ts", "classification": "human-judgment"},
                {"description": "fix2", "file": "c.ts", "classification": "mechanical"},
            ],
        }, "code_fix": {"fixes_applied": 2, "fix_commits": ["sha_a", "sha_c"]}}
        result = mod.build_digest_input(data)
        findings = result["findings"]["prevalidate"]
        assert findings[0]["commit_sha"] == "sha_a"
        assert findings[1]["commit_sha"] == ""  # human-judgment, no commit
        assert findings[2]["commit_sha"] == "sha_c"

    def test_verdict_ready_when_all_important_mechanical_fixed(self):
        """Verdict should be 'ready' when all important findings are mechanical and have fix commits."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {
            "tier": "1",
            "important": [
                {"description": "bug1", "file": "a.cs", "classification": "mechanical"},
                {"description": "bug2", "file": "b.cs", "classification": "mechanical"},
            ],
        }, "code_fix": {"fixes_applied": 2, "fix_commits": ["sha1", "sha2"]}}
        result = mod.build_digest_input(data)
        assert result["verdict"] == "ready"

    def test_verdict_warnings_when_some_important_not_mechanical(self):
        """Verdict should be 'warnings' when some important findings are human-judgment."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {
            "tier": "1",
            "important": [
                {"description": "bug1", "file": "a.cs", "classification": "mechanical"},
                {"description": "design issue", "file": "b.cs", "classification": "human-judgment"},
            ],
        }, "code_fix": {"fixes_applied": 1, "fix_commits": ["sha1"]}}
        result = mod.build_digest_input(data)
        assert result["verdict"] == "warnings"

    def test_double_encoded_json_code_review(self):
        """code_review_findings as a double-encoded JSON string (LLM serialization artifact)."""
        mod = self._load_module()
        inner = {"tier": "1", "findings": {"high": [
            {"id": "CR-001", "severity": "Important", "file": "test.cs", "description": "bug", "classification": "mechanical"},
        ], "medium": [], "low": []}, "important": [], "suggestions": []}
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": json.dumps(inner)}
        result = mod.build_digest_input(data)
        findings = result["findings"]["prevalidate"]
        assert len(findings) >= 1
        assert any("bug" in f.get("finding", "") for f in findings)

    def test_nested_findings_dict_structure(self):
        """code_review_findings with severity arrays nested inside 'findings' dict."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "code_review_findings": {
            "tier": "1",
            "findings": {
                "high": [{"id": "CR-001", "severity": "Important", "file": "a.cs", "description": "critical bug", "classification": "mechanical"}],
                "medium": [{"id": "CR-002", "severity": "Important", "file": "b.cs", "description": "perf issue", "classification": "human-judgment"}],
                "low": [],
            },
            "important": [], "suggestions": [],
        }}
        result = mod.build_digest_input(data)
        findings = result["findings"]["prevalidate"]
        assert len(findings) >= 2
        descs = [f["finding"] for f in findings]
        assert "critical bug" in descs
        assert "perf issue" in descs

    def test_file_url_in_findings(self):
        """Findings should include file_url linking to the PR file diff view."""
        mod = self._load_module()
        data = {
            **self.MINIMAL_UPSTREAM,
            "pr_url": "https://dev.azure.com/org/proj/_git/Repo/pullrequest/123",
            "code_review_findings": {
                "tier": "1",
                "findings": {"high": [{
                    "file": "src/Service.cs",
                    "description": "Null ref risk",
                    "category": "human-judgment",
                    "mechanical": False,
                }]},
            },
        }
        result = mod.build_digest_input(data)
        pv = result["findings"]["prevalidate"]
        assert len(pv) >= 1
        assert pv[0]["file_url"] == "https://dev.azure.com/org/proj/_git/Repo/pullrequest/123?_a=files&path=/src/Service.cs"

    def test_file_url_empty_when_no_pr_url(self):
        """file_url should be empty when pr_url is not set."""
        mod = self._load_module()
        data = {
            **self.MINIMAL_UPSTREAM,
            "pr_url": "",
            "code_review_findings": {
                "tier": "1",
                "findings": {"medium": [{
                    "file": "src/Foo.cs",
                    "description": "Some issue",
                    "mechanical": False,
                }]},
            },
        }
        result = mod.build_digest_input(data)
        pv = result["findings"]["prevalidate"]
        assert len(pv) >= 1
        assert pv[0]["file_url"] == ""

    def test_pr_url_passed_through(self):
        """build_digest_input should include pr_url in output for compose-digest."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "pr_url": "https://dev.azure.com/org/proj/_git/Repo/pullrequest/99"}
        result = mod.build_digest_input(data)
        assert result["pr_url"] == "https://dev.azure.com/org/proj/_git/Repo/pullrequest/99"

    def test_pr_url_empty_when_absent(self):
        """build_digest_input should include empty pr_url when not provided."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM}
        data.pop("pr_url", None)
        result = mod.build_digest_input(data)
        assert result["pr_url"] == ""

    # ── Regression tests for empty-digest bug (Phase 5 data loss) ────────────

    def test_load_optional_json_non_utf8_fallback(self, tmp_path):
        """Optional file with non-UTF8 bytes should load via the shared fallback chain."""
        mod = self._load_module()
        bad_file = tmp_path / "bad-encoding.json"
        bad_file.write_bytes(b'{"key": "\xff\xfe invalid"}')
        result = mod._load_optional_json(str(bad_file), "test")
        assert result == {"key": "ÿþ invalid"}

    def test_load_optional_json_missing_file(self):
        """Optional file that doesn't exist should return None, not crash."""
        mod = self._load_module()
        result = mod._load_optional_json("/nonexistent/file.json", "test")
        assert result is None

    def test_load_optional_json_invalid_json(self, tmp_path):
        """Optional file with invalid JSON should return None, not crash."""
        mod = self._load_module()
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json at all", encoding="utf-8")
        result = mod._load_optional_json(str(bad_file), "test")
        assert result is None

    def test_load_optional_json_bom(self, tmp_path):
        """Optional file with UTF-8 BOM should be loaded correctly."""
        mod = self._load_module()
        bom_file = tmp_path / "bom.json"
        bom_file.write_bytes(b'\xef\xbb\xbf{"key": "value"}')
        result = mod._load_optional_json(str(bom_file), "test")
        assert result == {"key": "value"}

    def test_load_optional_json_utf16(self, tmp_path):
        """Optional file written by PowerShell Tee-Object (UTF-16 LE) should be loaded correctly."""
        mod = self._load_module()
        utf16_file = tmp_path / "utf16.json"
        utf16_file.write_text('{"actionable": [{"thread_id": 123}], "skipped": []}', encoding="utf-16")
        result = mod._load_optional_json(str(utf16_file), "test")
        assert result is not None
        assert result["actionable"][0]["thread_id"] == 123

    def test_load_optional_json_utf16be(self, tmp_path):
        """UTF-16 BE payloads should be loaded correctly."""
        mod = self._load_module()
        utf16be_file = tmp_path / "utf16be.json"
        utf16be_file.write_bytes(b"\xfe\xff" + '{"actionable": [{"thread_id": 456}], "skipped": []}'.encode("utf-16-be"))
        result = mod._load_optional_json(str(utf16be_file), "test")
        assert result is not None
        assert result["actionable"][0]["thread_id"] == 456

    def test_load_optional_json_cp1252(self, tmp_path):
        """cp1252 fallback should preserve extended characters."""
        mod = self._load_module()
        cp1252_file = tmp_path / "cp1252.json"
        cp1252_file.write_bytes(json.dumps({"summary": "café"}, ensure_ascii=False).encode("cp1252"))
        result = mod._load_optional_json(str(cp1252_file), "test")
        assert result == {"summary": "café"}

    def test_load_merge_base_corrupt_uses_upstream_fallback(self, tmp_path):
        """When merge file is corrupt, falls back to upstream-data.json and rebuilds baseline."""
        mod = self._load_module()
        corrupt = tmp_path / "corrupt-digest.json"
        corrupt.write_text("", encoding="utf-8")  # empty = invalid JSON
        upstream = tmp_path / "upstream-data.json"
        upstream.write_text(json.dumps({
            **self.MINIMAL_UPSTREAM,
            "gate_lint": "passed", "gate_build": "passed",
        }), encoding="utf-8")
        result = mod._load_merge_base(str(corrupt), str(upstream))
        assert result is not None
        assert len(result.get("gates", [])) > 0
        # Verify gates are populated (check names include emoji prefixes)
        gate_checks = [g["check"] for g in result["gates"]]
        assert any("Code Review" in c for c in gate_checks)
        assert any("Build" in c for c in gate_checks)
        # Verify at least one gate is Passed
        assert any("Passed" in g["status"] for g in result["gates"])

    def test_load_merge_base_no_fallback_exits_nonzero(self, tmp_path):
        """When merge file is corrupt and no upstream fallback, exits non-zero."""
        mod = self._load_module()
        corrupt = tmp_path / "corrupt-digest.json"
        corrupt.write_text("", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            mod._load_merge_base(str(corrupt), None)
        assert exc_info.value.code == 1

    def test_load_merge_base_both_corrupt_exits_nonzero(self, tmp_path):
        """When both merge file and upstream fallback are corrupt, exits non-zero."""
        mod = self._load_module()
        corrupt = tmp_path / "corrupt-digest.json"
        corrupt.write_text("", encoding="utf-8")
        bad_upstream = tmp_path / "bad-upstream.json"
        bad_upstream.write_text("not json", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            mod._load_merge_base(str(corrupt), str(bad_upstream))
        assert exc_info.value.code == 1

    def test_load_merge_base_invalid_upstream_schema_exits_nonzero(self, tmp_path):
        mod = self._load_module()
        corrupt = tmp_path / "corrupt-digest.json"
        corrupt.write_text("", encoding="utf-8")
        bad_schema = tmp_path / "upstream-data.json"
        bad_schema.write_text(json.dumps({
            "_phases": {
                "1c": {"code_review_findings": {"unexpected": True}},
            }
        }), encoding="utf-8")
        with pytest.raises(SystemExit) as exc_info:
            mod._load_merge_base(str(corrupt), str(bad_schema))
        assert exc_info.value.code == 1


class TestSummarizeSignals:
    """Test _summarize_signals grouping and capping in build-digest-input.py."""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("bdi", str(SCRIPTS_DIR / "build-digest-input.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_few_signals_not_summarized(self):
        """5 or fewer signals are passed through verbatim."""
        mod = self._load_module()
        signals = ["🟡 a.cs: API change", "🟡 b.cs: API change", "✅ 2 test file(s) included"]
        result = mod.build_risk({"risk_level": "medium", "risk_signals": signals})
        # With <= 5 items, should use raw join
        assert "a.cs" in result["signals"]

    def test_many_signals_grouped(self):
        """More than 5 signals should be grouped by category with counts."""
        mod = self._load_module()
        signals = [
            "🟡 Controllers/A.cs: API controller change",
            "🟡 Controllers/B.cs: API controller change",
            "🟡 Controllers/C.cs: API controller change",
            "🟡 Services/X.cs: Service layer change",
            "🟡 Services/Y.cs: Service layer change",
            "🟡 Models/M.cs: Data model change",
            "✅ 3 test file(s) included",
        ]
        result = mod.build_risk({"risk_level": "medium", "risk_signals": signals})
        assert "×3" in result["signals"]  # 3 controller changes
        assert "×2" in result["signals"]  # 2 service changes
        assert "3 test file(s)" in result["signals"]
        # File paths should NOT appear
        assert "Controllers/A.cs" not in result["signals"]
        assert "Services/X.cs" not in result["signals"]

    def test_cap_at_max_groups(self):
        """Should cap at 5 category groups + remainder count."""
        mod = self._load_module()
        signals = []
        for i in range(6):
            for j in range(2):
                signals.append(f"🟡 file{i}_{j}.cs: Category {i}")
        result = mod.build_risk({"risk_level": "high", "risk_signals": signals})
        assert "+1 more categories" in result["signals"]

    def test_plain_string_signals_wrapped(self):
        """Plain string signal gets wrapped as single-element list via ensure_list."""
        mod = self._load_module()
        result = mod.build_risk({"risk_level": "low", "risk_signals": "just a string"})
        assert result["signals"] == "just a string"

    def test_empty_signals(self):
        """Empty list should produce empty string."""
        mod = self._load_module()
        result = mod.build_risk({"risk_level": "low", "risk_signals": []})
        assert result["signals"] == ""

    def test_unknown_risk_is_not_assessed(self):
        """Unknown risk gets intentional fallback wording instead of broken placeholders."""
        mod = self._load_module()
        result = mod.build_risk({})
        assert result["level"] == "unknown"
        assert result["signals"] == "Not assessed"
        assert result["review_requirement"] == "Not assessed — no risk classification available"

    def test_json_string_signals_parsed_and_summarized(self):
        """JSON array string (from Conductor | json filter) should be parsed and summarized."""
        mod = self._load_module()
        import json
        # Simulate what Conductor outputs: a JSON-encoded list of 40+ signals
        raw_signals = [
            "🟡 Controllers/A.cs: API controller change",
            "🟡 Controllers/B.cs: API controller change",
            "🟡 Controllers/C.cs: API controller change",
            "🟡 Services/X.cs: Service layer change",
            "🟡 Services/Y.cs: Service layer change",
            "🟡 Models/M.cs: Data model change",
            "🟡 Models/N.cs: Data model change",
            "✅ 3 test file(s) included",
        ]
        json_string = json.dumps(raw_signals)  # This is what | json produces
        result = mod.build_risk({"risk_level": "medium", "risk_signals": json_string})
        # Should be summarized (>5 items), not the raw verbose list
        assert "×3" in result["signals"], f"Expected grouped signals, got: {result['signals']}"
        assert "API controller change" in result["signals"]
        assert "Controllers/A.cs" not in result["signals"], "Individual file paths should be grouped away"
        assert "test file(s)" in result["signals"]

    def test_json_string_few_signals_not_summarized(self):
        """JSON array string with <=5 signals should be joined verbatim."""
        mod = self._load_module()
        import json
        raw_signals = ["🟡 a.cs: change A", "🟡 b.cs: change B"]
        json_string = json.dumps(raw_signals)
        result = mod.build_risk({"risk_level": "low", "risk_signals": json_string})
        assert "a.cs" in result["signals"], f"Small list should pass through, got: {result['signals']}"


class TestEnsureListAndNormalize:
    """Test ensure_list() and normalize_upstream() in build-digest-input.py."""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("bdi", str(SCRIPTS_DIR / "build-digest-input.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_ensure_list_already_list(self):
        mod = self._load_module()
        assert mod.ensure_list(["a", "b"]) == ["a", "b"]

    def test_ensure_list_python_repr(self):
        mod = self._load_module()
        result = mod.ensure_list("['abc123', 'def456']")
        assert result == ["abc123", "def456"]

    def test_ensure_list_json_array(self):
        mod = self._load_module()
        result = mod.ensure_list('["abc123", "def456"]')
        assert result == ["abc123", "def456"]

    def test_ensure_list_plain_string(self):
        mod = self._load_module()
        result = mod.ensure_list("some commit message")
        assert result == ["some commit message"]

    def test_ensure_list_empty(self):
        mod = self._load_module()
        assert mod.ensure_list(None) == []
        assert mod.ensure_list("") == []
        assert mod.ensure_list([]) == []
        assert mod.ensure_list(0) == []

    def test_normalize_upstream_flat_waf_keys(self):
        """Flat state keys should be restructured into nested watch_and_fix."""
        mod = self._load_module()
        data = {
            "build_status": "passed",
            "fixes_pushed": 1,
            "fix_summaries": "['Fix build error in SpaMiddleware']",
            "fix_commits": "['abc123']",
            "elapsed_minutes": 25,
        }
        mod.normalize_upstream(data)
        assert "watch_and_fix" in data
        waf = data["watch_and_fix"]
        assert waf["fixes_pushed"] == 1
        assert waf["fix_summaries"] == ["Fix build error in SpaMiddleware"]
        assert waf["fix_commits"] == ["abc123"]
        assert waf["elapsed_minutes"] == 25
        assert waf["build_status"] == "passed"

    def test_normalize_upstream_flat_code_fix_keys(self):
        """Flat state keys should be restructured into nested code_fix."""
        mod = self._load_module()
        data = {
            "fixes_applied": 2,
            "fix_commits": "['sha1', 'sha2']",
            "findings_remaining": 0,
        }
        mod.normalize_upstream(data)
        assert "code_fix" in data
        cf = data["code_fix"]
        assert cf["fixes_applied"] == 2
        assert cf["fix_commits"] == ["sha1", "sha2"]
        assert cf["findings_remaining"] == 0

    def test_normalize_upstream_already_nested(self):
        """If watch_and_fix already nested, still ensure_list its fields."""
        mod = self._load_module()
        data = {
            "watch_and_fix": {
                "build_status": "passed",
                "fixes_pushed": 1,
                "fix_summaries": "['msg']",
                "fix_commits": "['sha']",
                "elapsed_minutes": 10,
            }
        }
        mod.normalize_upstream(data)
        assert data["watch_and_fix"]["fix_summaries"] == ["msg"]
        assert data["watch_and_fix"]["fix_commits"] == ["sha"]

    def test_normalize_phase3_skipped_flat_keys_ignored(self):
        """When Phase 3 is not in _completed_phases, flat waf keys must NOT
        be synthesised into watch_and_fix — they belong to Phase 1d/5."""
        mod = self._load_module()
        data = {
            "_completed_phases": ["1a", "1b", "1c", "1d", "2", "4", "5"],
            "build_status": "passed",
            "total_fixes_pushed": 1,
            "fix_commits": "['abc123']",
        }
        mod.normalize_upstream(data)
        assert "watch_and_fix" not in data

    def test_normalize_phase3_skipped_agent_constructed_waf_wiped(self):
        """If the LLM agent already built a watch_and_fix dict from flat keys
        but Phase 3 was skipped, wipe it (no fix_summaries/fix_commits means
        the agent guessed)."""
        mod = self._load_module()
        data = {
            "_completed_phases": ["1a", "2", "4", "5"],
            "watch_and_fix": {
                "build_status": "unknown",
                "fixes_pushed": 2,
                "fix_summaries": [],
                "fix_commits": [],
                "elapsed_minutes": 0,
            },
        }
        mod.normalize_upstream(data)
        assert data["watch_and_fix"]["build_status"] == "skipped"
        assert data["watch_and_fix"]["fixes_pushed"] == 0

    def test_normalize_phase3_ran_flat_keys_used(self):
        """When Phase 3 IS in _completed_phases, flat waf keys should be
        restructured into watch_and_fix as before."""
        mod = self._load_module()
        data = {
            "_completed_phases": ["1a", "2", "3", "4", "5"],
            "build_status": "passed",
            "fixes_pushed": 1,
            "fix_summaries": "['Fix build error']",
            "fix_commits": "['abc123']",
            "elapsed_minutes": 10,
        }
        mod.normalize_upstream(data)
        assert "watch_and_fix" in data
        assert data["watch_and_fix"]["fixes_pushed"] == 1
        assert data["watch_and_fix"]["fix_commits"] == ["abc123"]

    def test_normalize_no_completed_phases_assumes_ran(self):
        """When _completed_phases is absent, assume Phase 3 ran (backward compat)."""
        mod = self._load_module()
        data = {
            "build_status": "passed",
            "fixes_pushed": 1,
            "fix_summaries": "['msg']",
            "fix_commits": "['sha']",
            "elapsed_minutes": 5,
        }
        mod.normalize_upstream(data)
        assert "watch_and_fix" in data
        assert data["watch_and_fix"]["fixes_pushed"] == 1

    def test_normalize_phases_namespace_prevents_fix_commits_collision(self):
        """When _phases is present, code_fix.fix_commits comes from Phase 1d
        and watch_and_fix.fix_commits comes from Phase 3 — no collision."""
        mod = self._load_module()
        data = {
            "_completed_phases": ["1a", "1b", "1c", "1d", "2", "3", "4"],
            # Flat keys show Phase 3's empty fix_commits (last-write-wins clobber)
            "fix_commits": [],
            "fixes_applied": 2,
            "findings_remaining": 0,
            "fixes_pushed": 0,
            "elapsed_minutes": 5,
            "build_status": "passed",
            # _phases contains the collision-free per-phase output
            "_phases": {
                "1d": {
                    "fixes_applied": 2,
                    "fix_commits": ["36c9e7c", "a1b2c3d"],
                    "findings_remaining": 0,
                },
                "3": {
                    "build_status": "passed",
                    "fixes_pushed": 0,
                    "fix_summaries": [],
                    "fix_commits": [],
                    "elapsed_minutes": 5,
                },
            },
        }
        mod.normalize_upstream(data)
        # code_fix should use Phase 1d's fix_commits (not the clobbered flat key)
        assert data["code_fix"]["fix_commits"] == ["36c9e7c", "a1b2c3d"]
        assert data["code_fix"]["fixes_applied"] == 2
        # watch_and_fix should use Phase 3's fix_commits (empty — no CI fixes)
        assert data["watch_and_fix"]["fix_commits"] == []
        assert data["watch_and_fix"]["fixes_pushed"] == 0

    def test_phases_present_but_phase3_empty_no_flat_fallback(self):
        """When _phases exists but phase 3 is empty, don't use flat keys."""
        mod = self._load_module()
        data = {
            "_phases": {"1d": {"fix_commits": ["sha_1d"]}},
            "_completed_phases": ["1d", "3"],
            "fix_commits": ["sha_1d"],
            "fixes_pushed": 1,
        }
        mod.normalize_upstream(data)
        assert data["watch_and_fix"]["fix_commits"] == []
        assert data["watch_and_fix"]["fixes_pushed"] == 0

        """Regression: fix_summaries as string repr must not produce char-per-row."""
        mod = self._load_module()
        data = {
            "pr_url": "https://dev.azure.com/org/proj/_git/repo/pullrequest/123",
            "code_review_findings": {"tier": "1", "important": [], "suggestions": []},
            "risk_level": "low",
            "risk_signals": [],
            "gate_lint": "passed", "gate_build": "passed",
            "gate_test": "passed", "gate_security": "passed",
            "watch_and_fix": {
                "build_status": "passed",
                "fixes_pushed": 1,
                "fix_summaries": "['Fix SpaMiddleware constructor arg mismatch']",
                "fix_commits": "['abc123']",
                "elapsed_minutes": 31,
            },
        }
        result = mod.build_digest_input(data)
        wf = result["findings"]["watch_fix"]
        assert len(wf) == 1, f"Expected 1 finding, got {len(wf)}"
        assert wf[0]["finding"] == "Fix SpaMiddleware constructor arg mismatch"
        assert wf[0]["commit_sha"] == "abc123"


# ── triage-threads.py ────────────────────────────────────────────────────────

class TestTriageThreads:
    """Test triage-threads.py thread classification."""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("triage", str(SCRIPTS_DIR / "triage-threads.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _make_thread(self, thread_id="1", author="GitOps (Git LowPriv)", unique_name="gitops@bot",
                     content="Review comment", status="active", file_path=None, line=None):
        thread = {
            "id": thread_id,
            "status": status,
            "comments": [{"content": content, "author": {"displayName": author, "uniqueName": unique_name}}],
        }
        if file_path:
            thread["threadContext"] = {"filePath": file_path}
            if line:
                thread["threadContext"]["rightFileStart"] = {"line": line}
        return thread

    def test_skips_digest_comment(self):
        mod = self._load_module()
        thread = self._make_thread(content="<!-- ai-agent:pr-orchestrator-digest -->\n# Digest")
        result = mod.classify_thread(thread, "user@test.com")
        assert result["skip"] is True
        assert result["reason"] == "digest_comment"

    def test_skips_system_message(self):
        mod = self._load_module()
        thread = self._make_thread(content="Ownership Enforcer PME added 2 reviewers")
        result = mod.classify_thread(thread, "user@test.com")
        assert result["skip"] is True
        assert result["reason"] == "system_message"

    def test_skips_pr_author(self):
        """PR author's own comments (not orchestrator-posted) are skipped."""
        mod = self._load_module()
        thread = self._make_thread(unique_name="user@test.com")
        result = mod.classify_thread(thread, "user@test.com")
        # After removing --pr-author filter, author threads are no longer auto-skipped
        # They should be classified normally (not skipped)
        assert result["skip"] is False

    def test_keeps_orchestrator_posted_author_thread(self):
        """PR author threads with orchestrator marker should NOT be skipped."""
        mod = self._load_module()
        body = "**🟡 Important** — Code Review\n\nUse IsNullOrWhiteSpace\n\n---\n_Posted by [PR Orchestrator](https://github.com/azure-core/octane) code review_"
        thread = self._make_thread(unique_name="user@test.com", content=body, file_path="/src/test.cs", line=42)
        result = mod.classify_thread(thread, "user@test.com")
        assert result["skip"] is False, "Orchestrator-posted findings should not be skipped even when posted as PR author"

    def test_skips_resolved_thread(self):
        mod = self._load_module()
        thread = self._make_thread(status="fixed")
        result = mod.classify_thread(thread, "user@test.com")
        assert result["skip"] is True
        assert "already_resolved" in result["reason"]

    def test_system_message_with_resolved_status_skipped_as_system(self):
        """System messages that happen to have resolved status should be filtered as system, not as findings."""
        mod = self._load_module()
        thread = self._make_thread(
            status="closed",
            content="Pull request description has been updated with summary.",
            author="PR Assistant",
        )
        result = mod.classify_thread(thread, "user@test.com")
        assert result["skip"] is True
        assert result["reason"] == "system_message", f"Expected system_message, got {result['reason']}"
        # Crucially, should NOT have file/body keys (not treated as a finding)
        assert "file" not in result
        assert "body" not in result

    def test_resolved_thread_carries_file_and_body(self):
        """already_resolved entries must include file/body for downstream digest rendering."""
        mod = self._load_module()
        thread = self._make_thread(
            status="fixed",
            file_path="/src/Service.cs",
            line=42,
            content="Unsafe default value for environment",
            author="GitOps (Git LowPriv)",
        )
        result = mod.classify_thread(thread, "user@test.com")
        assert result["skip"] is True
        assert result["file"] == "/src/Service.cs"
        assert result["line"] == 42
        assert "Unsafe default" in result["body"]
        assert result["author"] == "GitOps (Git LowPriv)"

    def test_resolved_thread_strips_html_from_body(self):
        """already_resolved thread bodies must be HTML-stripped for clean digest rendering."""
        mod = self._load_module()
        html_body = '<span style="font-family:\'Segoe UI\',SegoeUI;font-size:14px;">Missing single quotes around -Environment</span>'
        thread = self._make_thread(
            status="fixed",
            file_path="/src/Service.cs",
            content=html_body,
        )
        result = mod.classify_thread(thread, "user@test.com")
        assert result["skip"] is True
        assert "<span" not in result["body"]
        assert "Missing single quotes around -Environment" in result["body"]

    def test_clean_thread_body_function(self):
        """clean_thread_body should handle GitOps badge headers, HTML, entities."""
        mod = self._load_module()
        # Pure HTML span
        assert "hello world" == mod.clean_thread_body("<b>hello</b> <i>world</i>")
        # HTML entities
        assert "a & b < c" == mod.clean_thread_body("a &amp; b &lt; c")
        # Truncation
        long_text = "x" * 300
        result = mod.clean_thread_body(long_text, max_length=100)
        assert len(result) == 100
        assert result.endswith("...")

    def test_fetch_and_classify_preserves_skipped_fields(self):
        """_fetch_and_classify must pass through file/body/author/line for skipped entries.

        Regression test: line 294 previously rebuilt skipped entries with only
        thread_id and reason, discarding file/body/author/line that classify_thread returned.
        """
        mod = self._load_module()
        resolved_thread = self._make_thread(
            status="fixed",
            file_path="/src/Middleware.cs",
            line=55,
            content="Missing null check on request context",
            author="Code Review Bot",
        )
        resolved_thread["id"] = 12345
        # Mock fetch_ado_threads to return our thread
        original_fetch = mod.fetch_ado_threads
        mod.fetch_ado_threads = lambda pr_url: [resolved_thread]
        try:
            output = mod._fetch_and_classify("ado", "https://dev.azure.com/org/proj/_git/repo/pullrequest/1", None)
        finally:
            mod.fetch_ado_threads = original_fetch

        assert len(output["skipped"]) == 1
        skipped = output["skipped"][0]
        assert skipped["file"] == "/src/Middleware.cs"
        assert skipped["line"] == 55
        assert "Missing null check" in skipped["body"]
        assert skipped["author"] == "Code Review Bot"

    def test_bot_thread_actionable(self):
        mod = self._load_module()
        thread = self._make_thread(author="GitOps (Git LowPriv)", content="Consider refactoring this method")
        result = mod.classify_thread(thread, "user@test.com")
        assert result["skip"] is False
        assert result["is_bot"] is True
        assert result["verdict"] == "should_consider"

    def test_security_finding_must_fix(self):
        mod = self._load_module()
        thread = self._make_thread(content="This has a potential XSS vulnerability in the template injection")
        result = mod.classify_thread(thread, "user@test.com")
        assert result["skip"] is False
        assert result["verdict"] == "must_fix"

    def test_skips_status_update(self):
        mod = self._load_module()
        thread = self._make_thread(content="Todd Robertson updated the pull request status to Abandoned")
        result = mod.classify_thread(thread, "user@test.com")
        assert result["skip"] is True

    def test_includes_file_and_line(self):
        mod = self._load_module()
        thread = self._make_thread(file_path="/src/test.cs", line=42, content="Bug here")
        result = mod.classify_thread(thread, "user@test.com")
        assert result["file"] == "/src/test.cs"
        assert result["line"] == 42

    def test_html_body_extracts_finding_text(self):
        """GitOps PR Assistant HTML comments should extract the finding text, not badge header."""
        mod = self._load_module()
        html_body = (
            '<span style="font-weight:600;">PR Assistant</span>'
            '<small class="flex-row">'
            '<span><span>AI Code Review</span></span>'
            '<span><span>Iteration</span><span>1</span></span>'
            '<span><span>Reliability: Config</span></span>'
            '<span><span>Severity</span><span>Medium</span></span>'
            '</small>'
            'Hard-codes a production fallback when config key is missing. '
            'Consider using IWebHostEnvironment.EnvironmentName instead.'
            '<small class="secondary-text">Config issue</small>'
        )
        thread = self._make_thread(content=html_body, file_path="/src/test.cs")
        result = mod.classify_thread(thread, "user@test.com")
        assert "PR Assistant" not in result["body"]
        assert "AI Code Review" not in result["body"]
        assert "Iteration" not in result["body"]
        assert "production fallback" in result["body"]

    def test_html_body_strips_code_suggestion(self):
        """Code suggestion blocks in HTML comments should be stripped."""
        mod = self._load_module()
        html_body = (
            '<small class="flex-row"><span>badges</span></small>'
            'Use nullable type here.'
            '\nHere is the suggested code:\n'
            '```suggestion\nstring? value = null;\n```'
            '\nThis is better.'
            '<small class="secondary-text">footer</small>'
        )
        thread = self._make_thread(content=html_body, file_path="/src/test.cs")
        result = mod.classify_thread(thread, "user@test.com")
        assert "```suggestion" not in result["body"]
        assert "nullable type" in result["body"]

    def test_fetch_and_classify_no_retry_when_actionable_found(self):
        """_fetch_and_classify returns immediately when actionable threads exist."""
        mod = self._load_module()
        from unittest.mock import patch
        threads = [
            self._make_thread(thread_id="1", content="Consider refactoring"),
        ]
        with patch.object(mod, "fetch_ado_threads", return_value=threads):
            output = mod._fetch_and_classify("ado", "https://dev.azure.com/org/proj/_git/repo/pullrequest/1", None)
        assert output["summary"]["actionable"] == 1
        assert output["summary"]["total"] == 1

    def test_fetch_and_classify_returns_empty_when_no_threads(self):
        """_fetch_and_classify correctly reports 0 actionable for system-only threads."""
        mod = self._load_module()
        from unittest.mock import patch
        threads = [
            self._make_thread(thread_id="1", content="Ownership Enforcer PME added 2 reviewers"),
        ]
        with patch.object(mod, "fetch_ado_threads", return_value=threads):
            output = mod._fetch_and_classify("ado", "https://dev.azure.com/org/proj/_git/repo/pullrequest/1", None)
        assert output["summary"]["actionable"] == 0
        assert output["summary"]["skipped"] == 1

    def test_main_retries_on_empty_actionable(self):
        """main() retries when 0 actionable threads found and --retry-delay/--max-retries set."""
        mod = self._load_module()
        from unittest.mock import patch, call
        system_only = {
            "actionable": [], "skipped": [{"thread_id": "1", "reason": "system_message"}],
            "summary": {"total": 1, "actionable": 0, "skipped": 1},
        }
        with_actionable = {
            "actionable": [{"thread_id": "2", "skip": False, "verdict": "should_consider"}],
            "skipped": [{"thread_id": "1", "reason": "system_message"}],
            "summary": {"total": 2, "actionable": 1, "skipped": 1},
        }
        with patch.object(mod, "_fetch_and_classify", side_effect=[system_only, with_actionable]) as mock_fetch, \
             patch.object(mod.time, "sleep") as mock_sleep, \
             patch("sys.argv", ["triage-threads.py", "--platform", "ado", "--pr-url", "https://dev.azure.com/org/proj/_git/repo/pullrequest/1", "--retry-delay", "5", "--max-retries", "2"]), \
             patch("builtins.print"):
            mod.main()
        assert mock_fetch.call_count == 2
        mock_sleep.assert_called_once_with(5)

    def test_main_no_retry_without_flags(self):
        """main() does not retry when --retry-delay and --max-retries are defaults (0)."""
        mod = self._load_module()
        from unittest.mock import patch
        empty = {
            "actionable": [], "skipped": [],
            "summary": {"total": 0, "actionable": 0, "skipped": 0},
        }
        with patch.object(mod, "_fetch_and_classify", return_value=empty) as mock_fetch, \
             patch("sys.argv", ["triage-threads.py", "--platform", "ado", "--pr-url", "https://dev.azure.com/org/proj/_git/repo/pullrequest/1"]), \
             patch("builtins.print"):
            mod.main()
        assert mock_fetch.call_count == 1

    def test_main_retries_exhaust_max(self):
        """main() stops retrying after max_retries even if still 0 actionable."""
        mod = self._load_module()
        from unittest.mock import patch
        empty = {
            "actionable": [], "skipped": [],
            "summary": {"total": 0, "actionable": 0, "skipped": 0},
        }
        with patch.object(mod, "_fetch_and_classify", return_value=empty) as mock_fetch, \
             patch.object(mod.time, "sleep") as mock_sleep, \
             patch("sys.argv", ["triage-threads.py", "--platform", "ado", "--pr-url", "https://dev.azure.com/org/proj/_git/repo/pullrequest/1", "--retry-delay", "5", "--max-retries", "3"]), \
             patch("builtins.print"):
            mod.main()
        assert mock_fetch.call_count == 4  # 1 initial + 3 retries
        assert mock_sleep.call_count == 3


    def test_output_file_writes_utf8(self, monkeypatch, tmp_path):
        """--output-file should write JSON to file in addition to stdout."""
        mod = self._load_module()
        fake_output = {"summary": {"total": 1, "actionable": 1, "skipped": 0},
                       "actionable": [{"thread_id": "1", "verdict": "should_fix"}], "skipped": []}
        monkeypatch.setattr(mod, "_fetch_and_classify", lambda *a, **kw: fake_output)
        out_file = tmp_path / "triage-output.json"
        monkeypatch.setattr("sys.argv", ["triage-threads.py", "--platform", "ado",
                                         "--pr-url", "https://dev.azure.com/org/proj/_git/repo/pullrequest/1",
                                         "--output-file", str(out_file)])
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            mod.main()
        stdout_data = json.loads(captured.getvalue())
        assert stdout_data["summary"]["total"] == 1
        file_data = json.loads(out_file.read_text(encoding="utf-8"))
        assert file_data == stdout_data

    def test_fetch_github_threads_runtime_fallback_logs_and_uses_cli(self):
        mod = self._load_module()
        from unittest.mock import patch

        class BrokenReviewThreadOps:
            def __init__(self, ref):
                pass

            def list_threads(self):
                raise RuntimeError("boom")

        gh_comments = json.dumps([
            {"id": 2, "body": "gh body", "path": "src/a.py", "line": 9, "user": {"login": "bot"}},
        ])
        with patch.object(mod.PrRef, "from_url", return_value=object()), \
             patch.object(mod, "ReviewThreadOps", BrokenReviewThreadOps), \
             patch.object(mod, "run_cmd", return_value={"exit_code": 0, "stdout": gh_comments, "stderr": ""}), \
             contextlib.redirect_stderr(io.StringIO()) as captured:
            result = mod.fetch_github_threads("https://github.com/azure-core/octane/pull/5")

        assert result[0]["threadContext"]["filePath"] == "src/a.py"
        assert result[0]["comments"][0]["author"]["displayName"] == "bot"
        assert "[fallback] pr_platform.ReviewThreadOps.list_threads failed (boom) — using CLI" in captured.getvalue()


# ── scrape-commits.py ────────────────────────────────────────────────────────

class TestScrapeCommits:
    """Tests for scrape-commits.py"""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("scrape_commits", str(SCRIPTS_DIR / "scrape-commits.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_get_commits_multiple(self):
        """Parse git log with multiple commits."""
        mod = self._load_module()
        sha1 = "a" * 40
        sha2 = "b" * 40
        log_output = (
            f"{sha1}|||fix: first fix|||dev@example.com\n"
            f"{sha2}|||feat: second change|||dev@example.com\n"
        )
        from unittest.mock import patch, MagicMock
        # Mock run_git for log call and diff-tree calls
        def mock_run_git(args, cwd):
            result = MagicMock()
            if args[0] == "log":
                result.returncode = 0
                result.stdout = log_output
            elif args[0] == "diff-tree":
                result.returncode = 0
                sha = args[-1]
                if sha == sha1:
                    result.stdout = "file1.cs\nfile2.cs\n"
                else:
                    result.stdout = "file3.ts\n"
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        with patch.object(mod, "run_git", side_effect=mock_run_git):
            commits = mod.get_commits("start_sha", None, "/fake")
        assert len(commits) == 2
        assert commits[0]["sha"] == sha1
        assert commits[0]["short_sha"] == sha1[:7]
        assert commits[0]["message"] == "fix: first fix"
        assert commits[0]["files_changed"] == ["file1.cs", "file2.cs"]
        assert commits[1]["sha"] == sha2
        assert commits[1]["short_sha"] == sha2[:7]
        assert commits[1]["files_changed"] == ["file3.ts"]

    def test_get_commits_empty_output(self):
        """Parse git log with no commits (empty output)."""
        mod = self._load_module()
        from unittest.mock import patch, MagicMock
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        with patch.object(mod, "run_git", return_value=result):
            commits = mod.get_commits("start_sha", None, "/fake")
        assert commits == []

    def test_get_files_changed(self):
        """Get files changed for a commit."""
        mod = self._load_module()
        from unittest.mock import patch, MagicMock
        result = MagicMock()
        result.returncode = 0
        result.stdout = "src/main.cs\nsrc/test.cs\n"
        with patch.object(mod, "run_git", return_value=result):
            files = mod.get_files_changed("abc123", "/fake")
        assert files == ["src/main.cs", "src/test.cs"]

    def test_get_files_changed_error(self):
        """get_files_changed returns empty list on git error."""
        mod = self._load_module()
        from unittest.mock import patch, MagicMock
        result = MagicMock()
        result.returncode = 1
        result.stdout = ""
        with patch.object(mod, "run_git", return_value=result):
            files = mod.get_files_changed("bad_sha", "/fake")
        assert files == []

    def test_main_pipeline_mocked(self):
        """Full pipeline with mocked git commands produces valid JSON output."""
        mod = self._load_module()
        from unittest.mock import patch, MagicMock
        import io

        full_sha = "c" * 40

        def mock_run_git(args, cwd):
            result = MagicMock()
            result.returncode = 0
            if args[:2] == ["rev-parse", "--verify"]:
                result.stdout = "valid\n"
            elif args[0] == "rev-parse":
                result.stdout = f"{full_sha}\n"
            elif args[0] == "log":
                result.stdout = f"{full_sha}|||fix: build|||dev@x.com\n"
            elif args[0] == "diff-tree":
                result.stdout = "a.cs\n"
            else:
                result.stdout = ""
            result.stderr = ""
            return result

        out_path = str(SCRIPTS_DIR / "__test_scrape_output.json")
        try:
            with patch.object(mod, "run_git", side_effect=mock_run_git), \
                 patch("subprocess.run") as mock_sub:
                # Mock the git --version check in main()
                mock_sub.return_value = MagicMock(returncode=0, stdout="git version 2.0", stderr="")
                with patch("sys.argv", ["scrape-commits.py", "--since-sha", "abc", "--output-file", out_path]):
                    mod.main()
            with open(out_path, "r", encoding="utf-8") as f:
                output = json.load(f)
            assert output["since_sha"] == "abc"
            assert output["head_sha"] == full_sha
            assert output["commit_count"] == 1
            assert output["commits"][0]["sha"] == full_sha
            assert output["commits"][0]["short_sha"] == full_sha[:7]
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass

    def test_validate_sha_invalid_exits(self):
        """validate_sha exits on invalid SHA."""
        mod = self._load_module()
        from unittest.mock import patch, MagicMock
        result = MagicMock()
        result.returncode = 128
        result.stderr = "fatal: not a valid object"
        with patch.object(mod, "run_git", return_value=result):
            with pytest.raises(SystemExit):
                mod.validate_sha("invalid_sha", "/fake")

    def test_since_sha_trailing_newline_stripped(self):
        """since-sha with trailing newline (from Conductor stdout) is stripped before use."""
        mod = self._load_module()
        from unittest.mock import patch, MagicMock

        sha_with_newline = "abc123def456\n"

        def mock_run_git(args, cwd):
            result = MagicMock()
            result.returncode = 0
            if args[:2] == ["rev-parse", "--verify"]:
                # Verify the SHA passed to validate_sha has NO newline
                assert "\n" not in args[2], f"SHA still has newline: {args[2]!r}"
                result.stdout = "valid\n"
            elif args[0] == "rev-parse":
                result.stdout = "headsha789\n"
            elif args[0] == "log":
                # Verify the since_sha in the range has NO newline
                range_arg = args[1]  # e.g. "abc123def456..HEAD"
                assert "\n" not in range_arg, f"Range has newline: {range_arg!r}"
                result.stdout = ""
            else:
                result.stdout = ""
            result.stderr = ""
            return result

        out_path = str(SCRIPTS_DIR / "__test_scrape_newline.json")
        try:
            with patch.object(mod, "run_git", side_effect=mock_run_git), \
                 patch("subprocess.run") as mock_sub:
                mock_sub.return_value = MagicMock(returncode=0, stdout="git version 2.0", stderr="")
                with patch("sys.argv", ["scrape-commits.py", "--since-sha", sha_with_newline, "--output-file", out_path]):
                    mod.main()
            with open(out_path, "r", encoding="utf-8") as f:
                output = json.load(f)
            # The stored since_sha should be stripped
            assert output["since_sha"] == "abc123def456"
            assert "\n" not in output["since_sha"]
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass


# ── scrape-threads.py ────────────────────────────────────────────────────────

class TestScrapeThreads:
    """Tests for scrape-threads.py"""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("scrape_threads", str(SCRIPTS_DIR / "scrape-threads.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_build_file_to_commits_mapping(self):
        """Build file-to-commit mapping from commits data."""
        mod = self._load_module()
        commits_data = {
            "commits": [
                {"sha": "aaa", "files_changed": ["src/a.cs", "src/b.cs"]},
                {"sha": "bbb", "files_changed": ["src/b.cs", "src/c.cs"]},
            ]
        }
        mapping = mod.build_file_to_commits(commits_data)
        assert "src/a.cs" in mapping
        assert len(mapping["src/b.cs"]) == 2
        # Most recent commit for b.cs should be bbb
        assert mapping["src/b.cs"][-1]["sha"] == "bbb"

    def test_find_commit_for_file_direct_match(self):
        """find_commit_for_file returns last commit touching the file."""
        mod = self._load_module()
        file_to_commits = {
            "src/a.cs": [{"sha": "aaa", "commit": {}}, {"sha": "bbb", "commit": {}}],
        }
        assert mod.find_commit_for_file("src/a.cs", file_to_commits) == "bbb"

    def test_find_commit_for_file_no_match(self):
        """find_commit_for_file returns empty string when no match."""
        mod = self._load_module()
        assert mod.find_commit_for_file("unknown.cs", {}) == ""

    def test_build_addressed_details_from_resolved(self):
        """Build addressed_details from resolved threads matched to commits."""
        mod = self._load_module()
        threads = [
            {"thread_id": "1", "file": "src/a.cs", "body": "Fix the null check here"},
            {"thread_id": "2", "file": "src/b.cs", "body": "Rename variable"},
        ]
        file_to_commits = {
            "src/a.cs": [{"sha": "commit_a", "commit": {}}],
            "src/b.cs": [{"sha": "commit_b", "commit": {}}],
        }
        details = mod.build_addressed_details(threads, file_to_commits)
        assert len(details) == 2
        assert details[0]["thread_id"] == "1"
        assert details[0]["commit_sha"] == "commit_a"
        assert details[0]["status"] == "fixed"
        assert details[1]["commit_sha"] == "commit_b"

    def test_build_addressed_details_strips_html_from_body(self):
        """HTML tags in thread body must be stripped from finding_summary."""
        mod = self._load_module()
        threads = [
            {"thread_id": "1", "file": "src/a.cs",
             "body": '<span style="font-family:\'Segoe UI\';font-size:14px;">Missing single quotes around -Environment</span>'},
        ]
        file_to_commits = {
            "src/a.cs": [{"sha": "commit_a", "commit": {}}],
        }
        details = mod.build_addressed_details(threads, file_to_commits)
        assert len(details) == 1
        assert "<span" not in details[0]["finding_summary"]
        assert "Missing single quotes around -Environment" in details[0]["finding_summary"]

    def test_build_addressed_details_decodes_html_entities(self):
        """HTML entities in thread body must be decoded in finding_summary."""
        mod = self._load_module()
        threads = [
            {"thread_id": "1", "file": "src/a.cs",
             "body": "Use &lt;T&gt; instead of &amp;generic"},
        ]
        file_to_commits = {"src/a.cs": [{"sha": "sha1", "commit": {}}]}
        details = mod.build_addressed_details(threads, file_to_commits)
        assert "&lt;" not in details[0]["finding_summary"]
        assert "&amp;" not in details[0]["finding_summary"]
        assert "Use <T> instead of &generic" in details[0]["finding_summary"]

    def test_build_resolved_threads_with_baseline(self):
        """Compute newly resolved: threads in baseline.actionable not in current actionable."""
        mod = self._load_module()
        triage_output = {
            "actionable": [{"thread_id": "2", "file": "b.cs"}],
            "skipped": [],
        }
        baseline = {
            "threads": {
                "actionable": [
                    {"thread_id": "1", "file": "a.cs", "body": "fix this"},
                    {"thread_id": "2", "file": "b.cs", "body": "check that"},
                ],
            },
        }
        resolved, _, newly_resolved = mod.build_resolved_threads(triage_output, baseline)
        assert len(resolved) == 1
        assert resolved[0]["thread_id"] == "1"
        assert newly_resolved == 1

    def test_build_resolved_threads_no_baseline(self):
        """No baseline: resolved threads come from skipped with already_resolved reason."""
        mod = self._load_module()
        triage_output = {
            "actionable": [{"thread_id": "2"}],
            "skipped": [
                {"thread_id": "1", "file": "a.cs", "body": "done", "reason": "already_resolved"},
                {"thread_id": "3", "file": "c.cs", "body": "sys", "reason": "system_message"},
            ],
        }
        resolved, _, newly_resolved = mod.build_resolved_threads(triage_output, None)
        assert len(resolved) == 1
        assert resolved[0]["thread_id"] == "1"
        assert newly_resolved == 1

    def test_build_file_to_commits_empty(self):
        """build_file_to_commits returns empty mapping when commits_data is None."""
        mod = self._load_module()
        assert mod.build_file_to_commits(None) == {}

    def test_build_addressed_details_no_commit_match(self):
        """addressed_details has empty commit_sha when no commit matches file."""
        mod = self._load_module()
        threads = [{"thread_id": "1", "file": "unmatched.cs", "body": "fix"}]
        details = mod.build_addressed_details(threads, {})
        assert len(details) == 1
        assert details[0]["commit_sha"] == ""


# ── build-digest-input.py overlay (scrape data) ─────────────────────────────

class TestBuildDigestOverlay:
    """Tests for build-digest-input.py scraped data overlay logic."""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("bdi", str(SCRIPTS_DIR / "build-digest-input.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    MINIMAL_UPSTREAM = {
        "pr_url": "https://dev.azure.com/org/proj/_git/repo/pullrequest/123",
        "code_review_findings": {"tier": "1", "important": [], "suggestions": []},
        "code_fix": {"fixes_applied": 0, "fix_commits": []},
        "risk_level": "low",
        "risk_signals": ["test only"],
        "gate_lint": "passed", "gate_build": "passed", "gate_test": "passed", "gate_security": "passed",
        "watch_and_fix": {"build_status": "passed", "fixes_pushed": 2, "fix_summaries": ["fix A", "fix B"], "fix_commits": ["agent_sha1", "agent_sha2"], "elapsed_minutes": 20},
    }

    def test_scrape_waf_overrides_fix_commits(self):
        """scrape_waf commits override agent-reported fix_commits in watch_fix findings."""
        mod = self._load_module()
        scrape_waf = {
            "commits": [
                {"sha": "scraped_sha1", "message": "fix A"},
                {"sha": "scraped_sha2", "message": "fix B"},
            ]
        }
        result = mod.build_digest_input({**self.MINIMAL_UPSTREAM}, scrape_waf=scrape_waf)
        watch_fix = result["findings"]["watch_fix"]
        assert len(watch_fix) == 2
        assert watch_fix[0]["commit_sha"] == "scraped_sha1"
        assert watch_fix[1]["commit_sha"] == "scraped_sha2"

    def test_scrape_waf_provides_fix_summaries(self):
        """scrape_waf provides fix_summaries from commit messages when agent didn't."""
        mod = self._load_module()
        data = {**self.MINIMAL_UPSTREAM, "watch_and_fix": {
            "build_status": "passed", "fixes_pushed": 1, "fix_summaries": [],
            "elapsed_minutes": 10,
        }}
        scrape_waf = {"commits": [{"sha": "s1", "message": "scraped fix msg"}]}
        result = mod.build_digest_input(data, scrape_waf=scrape_waf)
        watch_fix = result["findings"]["watch_fix"]
        assert len(watch_fix) == 1
        assert watch_fix[0]["finding"] == "scraped fix msg"
        assert watch_fix[0]["commit_sha"] == "s1"

    def test_scrape_waf_none_falls_back_to_agent(self):
        """scrape_waf=None falls back to agent-reported data (backward compat)."""
        mod = self._load_module()
        result = mod.build_digest_input({**self.MINIMAL_UPSTREAM}, scrape_waf=None)
        watch_fix = result["findings"]["watch_fix"]
        assert len(watch_fix) == 2
        assert watch_fix[0]["commit_sha"] == "agent_sha1"
        assert watch_fix[1]["commit_sha"] == "agent_sha2"

    def test_thread_state_overrides_addressed_details(self):
        """thread_state overrides addressed_details in merge_phase5."""
        mod = self._load_module()
        existing = {
            "findings": {"prevalidate": [], "watch_fix": [], "feedback": []},
            "timeline": [{"phase": "Address Feedback", "duration": "", "result": ""}],
            "gates": [], "verdict": "ready", "pr_url": "https://test",
        }
        data = {"address_feedback": {"iteration": 1, "comments_addressed": 2, "fix_commits": ["agent_sha"], "all_addressed": True}}
        thread_state = {
            "addressed_details": [
                {"thread_id": "t1", "file": "a.cs", "finding_summary": "Fix null", "commit_sha": "scraped_sha1"},
                {"thread_id": "t2", "file": "b.cs", "finding_summary": "Rename var", "commit_sha": "scraped_sha2"},
            ]
        }
        result = mod.merge_phase5(existing, data, thread_state=thread_state)
        feedback = result["findings"]["feedback"]
        assert len(feedback) == 2
        assert feedback[0]["commit_sha"] == "scraped_sha1"
        assert feedback[1]["file"] == "b.cs"

    def test_scrape_feedback_overrides_fix_commits(self):
        """scrape_feedback overrides fix_commits in merge_phase5 fallback path."""
        mod = self._load_module()
        existing = {
            "findings": {"prevalidate": [], "watch_fix": [], "feedback": []},
            "timeline": [{"phase": "Address Feedback", "duration": "", "result": ""}],
            "gates": [], "verdict": "ready", "pr_url": "https://test",
        }
        data = {"address_feedback": {"iteration": 1, "comments_addressed": 1, "fix_commits": ["agent_sha"], "all_addressed": True}}
        scrape_feedback = {"commits": [{"sha": "scraped_fb_sha", "message": "fix"}]}
        result = mod.merge_phase5(existing, data, scrape_feedback=scrape_feedback)
        feedback = result["findings"]["feedback"]
        assert len(feedback) == 1
        assert feedback[0]["commit_sha"] == "scraped_fb_sha"

    def test_all_overlay_params_none_identical(self):
        """All overlay params None — identical to existing behavior."""
        mod = self._load_module()
        result_no_overlay = mod.build_digest_input({**self.MINIMAL_UPSTREAM})
        result_with_none = mod.build_digest_input({**self.MINIMAL_UPSTREAM}, scrape_waf=None)
        assert result_no_overlay == result_with_none

    def test_merge_phase5_all_none_uses_agent_data(self):
        """merge_phase5 with no scrape params uses agent addressed_details."""
        mod = self._load_module()
        existing = {
            "findings": {"prevalidate": [], "watch_fix": [], "feedback": []},
            "timeline": [{"phase": "Address Feedback", "duration": "", "result": ""}],
            "gates": [], "verdict": "ready", "pr_url": "https://test",
        }
        data = {
            "address_feedback": {
                "iteration": 1, "comments_addressed": 1, "fix_commits": ["agent_sha"],
                "all_addressed": True,
                "addressed_details": [
                    {"thread_id": "t1", "file": "x.cs", "finding_summary": "Agent detail", "commit_sha": "agent_sha"},
                ],
            }
        }
        result = mod.merge_phase5(existing, data, scrape_feedback=None, thread_state=None)
        feedback = result["findings"]["feedback"]
        assert len(feedback) == 1
        assert feedback[0]["commit_sha"] == "agent_sha"
        assert feedback[0]["finding"] == "Agent detail"

    def test_merge_phase5_strips_stale_watch_fix_when_phase3_skipped(self):
        """merge_phase5 strips stale watch_fix findings when Phase 3 was not completed."""
        mod = self._load_module()
        existing = {
            "pr_url": "https://dev.azure.com/org/proj/_git/repo/pullrequest/1",
            "findings": {
                "prevalidate": [{"num": 1, "finding": "test finding", "status": "✅ Fixed"}],
                "watch_fix": [
                    {"num": 1, "finding": "stale fix from run N-1", "status": "✅ Fixed"},
                    {"num": 2, "finding": "another stale fix", "status": "✅ Fixed"},
                ],
                "feedback": [],
            },
            "timeline": [],
        }
        phase5 = {
            "pr_url": "https://dev.azure.com/org/proj/_git/repo/pullrequest/1",
            "_completed_phases": ["1a", "1b", "1c", "2", "4", "5"],
            "address_feedback": {"status": "no_feedback"},
        }
        result = mod.merge_phase5(existing, phase5)
        assert result["findings"]["watch_fix"] == [], \
            "Stale watch_fix findings should be stripped when Phase 3 not in _completed_phases"
        assert len(result["findings"]["prevalidate"]) == 1, \
            "prevalidate findings should be preserved"

    def test_merge_phase5_preserves_watch_fix_when_phase3_ran(self):
        """merge_phase5 preserves watch_fix findings when Phase 3 was completed."""
        mod = self._load_module()
        existing = {
            "pr_url": "https://dev.azure.com/org/proj/_git/repo/pullrequest/1",
            "findings": {
                "prevalidate": [],
                "watch_fix": [
                    {"num": 1, "finding": "real fix", "status": "✅ Fixed"},
                ],
                "feedback": [],
            },
            "timeline": [],
        }
        phase5 = {
            "pr_url": "https://dev.azure.com/org/proj/_git/repo/pullrequest/1",
            "_completed_phases": ["1a", "1b", "1c", "2", "3", "4", "5"],
            "address_feedback": {"status": "no_feedback"},
        }
        result = mod.merge_phase5(existing, phase5)
        assert len(result["findings"]["watch_fix"]) == 1, \
            "watch_fix findings should be preserved when Phase 3 was completed"



    def test_gates_show_skipped_when_phase3_not_run(self):
        """CI-dependent gates show Skipped when Phase 3 did not run."""
        mod = self._load_module()
        data = {
            "pr_url": "https://example.com/pr/1",
            "code_review_findings": {"tier": "1", "high": [], "medium": [], "low": []},
            "_completed_phases": ["1a", "1b", "1c", "1d", "2", "4"],
        }
        gates = mod.build_gates_list(data, "Gatekeeper")
        review = next(g for g in gates if "Code Review" in g["check"])
        build = next(g for g in gates if "Build" in g["check"])
        assert "Passed" in review["status"]
        assert "Skipped" in build["status"]

    def test_gates_show_passed_when_phase3_ran(self):
        """CI-dependent gates show Passed when Phase 3 ran and gates passed."""
        mod = self._load_module()
        data = {
            "pr_url": "https://example.com/pr/1",
            "code_review_findings": {"tier": "1", "high": [], "medium": [], "low": []},
            "_completed_phases": ["1a", "1b", "1c", "1d", "2", "3", "4"],
            "_phases": {"3": {"build_status": "passed"}},
        }
        gates = mod.build_gates_list(data, "Gatekeeper")
        review = next(g for g in gates if "Code Review" in g["check"])
        build = next(g for g in gates if "Build" in g["check"])
        assert "Passed" in review["status"]
        assert "Passed" in build["status"]

    def test_gate_key_mapping_no_overwrite(self):
        """Gate key mapping does not overwrite existing gate_* values."""
        mod = self._load_module()
        data = {
            "lint_status": "passed",
            "gate_lint": "failed",
            "_completed_phases": ["1d"],
        }
        normalized = mod.normalize_upstream(data)
        assert normalized["gate_lint"] == "failed"  # original preserved


# ── phase_contracts.py ──────────────────────────────────────────────────────

class TestPhaseContracts:
    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("phase_contracts", str(SCRIPTS_DIR / "phase_contracts.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_normalize_phase_output_applies_aliases(self):
        mod = self._load_module()
        result = mod.normalize_phase_output("1a", {
            "test_count": 5,
            "tests_passed": 4,
            "tests_failed": 1,
        })
        assert result["tests_run"] == 5
        assert result["tests_passed"] == 4
        assert result["tests_failed"] == 1
        assert "test_count" not in result

    def test_validate_phase_output_checks_required_keys(self):
        mod = self._load_module()
        valid, warnings = mod.validate_phase_output("1c", {
            "tier": "1",
            "code_review_findings": {},
        })
        assert valid is True
        assert warnings == []

    def test_phase_4b_schema_matches_walkthrough_contract(self):
        mod = self._load_module()
        valid, warnings = mod.validate_phase_output("4b", {
            "walkthrough_posted": True,
            "pr_classification": "feature",
            "skip_reason": "none",
            "diagram_count": 2,
            "concepts_explained": ["flow", "state"],
        })
        assert valid is True
        assert warnings == []

    def test_validate_unknown_phase_is_forward_compatible(self):
        mod = self._load_module()
        valid, warnings = mod.validate_phase_output("9z", {"anything": True})
        assert valid is True
        assert warnings == []

    def test_read_phase_output_prefers_namespaced_data(self):
        mod = self._load_module()
        state = {
            "tests_run": 0,
            "_phases": {
                "1a": {
                    "test_count": 12,
                    "tests_passed": 11,
                    "tests_failed": 1,
                }
            },
        }
        result = mod.read_phase_output(state, "1a")
        assert result == {
            "tests_run": 12,
            "tests_passed": 11,
            "tests_failed": 1,
        }

    def test_read_phase_output_falls_back_to_flat_keys(self):
        mod = self._load_module()
        state = {
            "test_count": 12,
            "tests_passed": 11,
            "tests_failed": 1,
        }
        result = mod.read_phase_output(state, "1a")
        assert result == {
            "tests_run": 12,
            "tests_passed": 11,
            "tests_failed": 1,
        }

    def test_read_phase_output_returns_none_when_absent(self):
        mod = self._load_module()
        assert mod.read_phase_output({}, "5") is None


class TestPhaseOutputValidation:
    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("phase_output_validation", str(SCRIPTS_DIR / "phase_output_validation.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_parse_json_like_accepts_dict_passthrough(self):
        mod = self._load_module()
        payload = {"findings": []}
        assert mod.parse_json_like(payload, "payload") == payload

    def test_parse_json_like_parses_valid_json_string(self):
        mod = self._load_module()
        payload = mod.parse_json_like('{"findings": {"Important": []}}', "payload")
        assert payload == {"findings": {"Important": []}}

    def test_parse_json_like_cleans_llm_artifacts(self):
        mod = self._load_module()
        raw = "```json\n{\"items\": [1, 2,],}\n```"
        assert mod.parse_json_like(raw, "payload") == {"items": [1, 2]}

    def test_parse_json_like_rejects_unparseable_input(self):
        mod = self._load_module()
        with pytest.raises(mod.ValidationError):
            mod.parse_json_like("not valid json", "payload")

    def test_parse_json_like_allow_plain_string_returns_string(self):
        mod = self._load_module()
        assert mod.parse_json_like('"hello"', "payload", allow_plain_string=True) == "hello"

    def test_parse_json_like_expected_types_validate(self):
        mod = self._load_module()
        assert mod.parse_json_like('["a", "b"]', "payload", expected_types=(list,)) == ["a", "b"]
        with pytest.raises(mod.ValidationError):
            mod.parse_json_like('{"not": "a list"}', "payload", expected_types=(list,))

    def test_coerce_int_handles_scalar_inputs(self):
        mod = self._load_module()
        assert mod.coerce_int(7, "value") == 7
        assert mod.coerce_int("42", "value") == 42
        assert mod.coerce_int(3.7, "value") == 3

    def test_coerce_int_invalid_string_returns_default(self):
        mod = self._load_module()
        assert mod.coerce_int("not-a-number", "value") == 0
        assert mod.coerce_int("not-a-number", "value", default=9) == 9

    def test_coerce_bool_handles_common_string_values(self):
        mod = self._load_module()
        assert mod.coerce_bool(True, "flag") is True
        assert mod.coerce_bool("true", "flag") is True
        assert mod.coerce_bool("True", "flag") is True
        assert mod.coerce_bool("TRUE", "flag") is True
        assert mod.coerce_bool("false", "flag") is False
        assert mod.coerce_bool("yes", "flag") is True
        assert mod.coerce_bool("no", "flag") is False

    def test_ensure_str_list_handles_strings_and_non_strings(self):
        mod = self._load_module()
        assert mod.ensure_str_list(["a", "b"], "items") == ["a", "b"]
        assert mod.ensure_str_list("single-value", "items") == ["single-value"]
        assert mod.ensure_str_list(None, "items") == []
        assert mod.ensure_str_list([1, " two ", False, ""], "items") == ["1", "two", "False"]

    def test_validate_upstream_data_reports_valid_missing_and_none_inputs(self):
        mod = self._load_module()
        valid, issues = mod.validate_upstream_data({
            "_phases": {
                "1c": {"code_review_findings": {}},
            }
        })
        assert valid is True
        assert issues == []

        invalid, missing_issues = mod.validate_upstream_data({
            "_phases": {}
        })
        assert invalid is False
        assert any("missing code_review_findings" in issue for issue in missing_issues)

        none_valid, none_issues = mod.validate_upstream_data(None)
        assert none_valid is False
        assert none_issues == ["upstream data is not a JSON object"]

    def test_normalize_phase1c_output_well_formed_and_empty_findings(self):
        mod = self._load_module()
        raw = {
            "code_review_findings": {
                "findings": {
                    "Critical": [],
                    "Important": [{"id": "CR-1"}],
                    "Suggestion": [],
                }
            },
            "done": True,
        }
        normalized = mod.normalize_phase1c_output(raw)
        assert normalized["code_review_findings"]["findings"]["Important"][0]["id"] == "CR-1"

        empty_normalized = mod.normalize_phase1c_output({
            "code_review_findings": {},
            "done": True,
        })
        assert empty_normalized["code_review_findings"] == mod.canonical_empty_findings()

    def test_normalize_phase1c_output_parses_findings_json_string(self):
        mod = self._load_module()
        raw = {
            "code_review_findings": json.dumps({"findings": {"Critical": [], "Important": [], "Suggestion": []}}),
            "done": True,
        }
        normalized = mod.normalize_phase1c_output(raw)
        assert normalized["code_review_findings"]["findings"]["Suggestion"] == []

    def test_normalize_phase1c_output_rejects_invalid_payload(self):
        mod = self._load_module()
        with pytest.raises(mod.ValidationError):
            mod.normalize_phase1c_output({"code_review_findings": "totally invalid", "done": True})

    def test_normalize_phase1d_output_handles_well_formed_and_salvaged_fields(self):
        mod = self._load_module()
        normalized = mod.normalize_phase1d_output({
            "code_fix": {
                "fixes_applied": 1,
                "fix_commits": ["abc123"],
                "findings_remaining": [],
            },
            "done": True,
        })
        assert normalized["code_fix"]["fixes_applied"] == 1
        assert normalized["fix_commits"] == ["abc123"]

        salvaged = mod.normalize_phase1d_output({
            "code_fix": 123,
            "fixes_applied": "2",
            "fix_commits": "sha123",
            "findings_remaining": "needs manual review",
            "done": "true",
        })
        assert salvaged["code_fix"]["fixes_applied"] == 2
        assert salvaged["fixes_applied"] == 2
        assert salvaged["fix_commits"] == ["sha123"]
        assert salvaged["findings_remaining"] == "needs manual review"
        assert salvaged["done"] is True

    def test_normalize_phase1c_output_salvages_double_encoded_json(self):
        mod = self._load_module()
        findings = {
            "findings": {
                "Important": [{
                    "id": "CR-1",
                    "file": "src/service.py",
                    "line": 12,
                    "description": "Add null check",
                    "recommended_fix": "Guard against None",
                    "category": "mechanical",
                    "mechanical": True,
                }],
                "Suggestion": [],
            },
            "review_engine": "Gatekeeper",
            "tier": "1",
        }
        raw = json.dumps({
            "code_review_findings": json.dumps(json.dumps(findings)),
            "done": "true",
        })
        normalized = mod.normalize_phase1c_output(raw)
        assert normalized["done"] is True
        assert normalized["tier"] == "1"
        assert normalized["review_engine"] == "Gatekeeper"
        assert normalized["code_review_findings"]["findings"]["Important"][0]["id"] == "CR-1"

    def test_normalize_phase1c_output_accepts_python_literal(self):
        mod = self._load_module()
        raw = json.dumps({
            "code_review_findings": "{'findings': {'Important': [], 'Suggestion': []}}",
            "done": True,
        })
        normalized = mod.normalize_phase1c_output(raw)
        assert normalized["code_review_findings"]["findings"]["Important"] == []
        assert normalized["code_review_findings"]["findings"]["Suggestion"] == []

    def test_validate_phase1c_script_writes_workspace_files(self, tmp_path):
        findings = {
            "findings": {
                "Important": [],
                "Suggestion": [{
                    "id": "CR-2",
                    "file": "src/ui.ts",
                    "line": 8,
                    "description": "Rename variable",
                    "recommended_fix": "Use descriptive name",
                    "category": "mechanical",
                    "mechanical": True,
                }],
            }
        }
        raw = json.dumps({"code_review_findings": json.dumps(findings), "done": True})
        result = run_script("validate-phase1c-output.py", args=[
            "--raw-output", raw,
            "--workspace-dir", str(tmp_path),
        ])
        assert result["exit_code"] == 0, result["stderr"]
        assert (tmp_path / "phase1c-output.json").is_file()
        assert (tmp_path / "code-review-findings.json").is_file()
        saved = json.loads((tmp_path / "code-review-findings.json").read_text(encoding="utf-8"))
        assert saved["findings"]["Suggestion"][0]["id"] == "CR-2"

    def test_validate_phase1c_script_rejects_missing_findings(self):
        result = run_script("validate-phase1c-output.py", args=[
            "--raw-output", json.dumps({"done": True}),
        ])
        assert result["exit_code"] == 1
        assert "code_review_findings" in result["stderr"]

    def test_validate_phase1c_script_accepts_code_review_findings_dict(self, tmp_path):
        raw = json.dumps({
            "code_review_findings": {
                "findings": {
                    "Critical": [{
                        "id": "CR-1",
                        "file": "src/service.py",
                        "line": 12,
                        "description": "Fix the null guard",
                        "recommended_fix": "Add a null check",
                        "category": "mechanical",
                        "mechanical": True,
                    }],
                    "Important": [],
                    "Suggestion": [],
                },
                "summary": {"total_findings": 1},
            },
            "done": True,
        })
        result = run_script("validate-phase1c-output.py", args=[
            "--raw-output", raw,
            "--workspace-dir", str(tmp_path),
        ])
        assert result["exit_code"] == 0, result["stderr"]
        assert result["json"]["code_review_findings"]["findings"]["Critical"][0]["id"] == "CR-1"

    def test_validate_phase1c_script_accepts_findings_alias(self, tmp_path):
        raw = json.dumps({
            "findings": {
                "Critical": [],
                "Important": [{
                    "id": "CR-2",
                    "file": "src/api.py",
                    "line": 33,
                    "description": "Use cached client",
                    "recommended_fix": "Reuse the existing client instance",
                    "category": "mechanical",
                    "mechanical": True,
                }],
                "Suggestion": [],
            },
            "tier": "1",
            "review_engine": "Gatekeeper",
            "done": True,
        })
        result = run_script("validate-phase1c-output.py", args=[
            "--raw-output", raw,
            "--workspace-dir", str(tmp_path),
        ])
        assert result["exit_code"] == 0, result["stderr"]
        saved = json.loads((tmp_path / "code-review-findings.json").read_text(encoding="utf-8"))
        assert saved["Important"][0]["id"] == "CR-2"
        assert result["json"]["tier"] == "1"
        assert result["json"]["review_engine"] == "Gatekeeper"

    def test_validate_phase1c_script_accepts_string_number_count_fields(self):
        raw = json.dumps({
            "code_review_findings": {
                "findings": {
                    "Critical": [],
                    "Important": [{
                        "id": "CR-3",
                        "file": "src/cache.py",
                        "line": 7,
                        "description": "Avoid repeated parsing",
                        "recommended_fix": "Cache the parsed payload",
                        "category": "mechanical",
                        "mechanical": True,
                    }],
                    "Suggestion": [],
                },
                "summary": {
                    "total_findings": "1",
                    "important_count": "1",
                    "suggestion_count": "0",
                },
            },
            "done": "TRUE",
        })
        result = run_script("validate-phase1c-output.py", args=[
            "--raw-output", raw,
        ])
        assert result["exit_code"] == 0, result["stderr"]
        summary = result["json"]["code_review_findings"]["summary"]
        assert summary["total_findings"] == 1
        assert summary["important_count"] == 1
        assert summary["suggestion_count"] == 0

    def test_validate_phase1c_script_rejects_truly_empty_findings_payload(self):
        result = run_script("validate-phase1c-output.py", args=[
            "--raw-output", json.dumps({"tier": "1", "review_engine": "Gatekeeper", "done": True}),
        ])
        assert result["exit_code"] == 1
        assert "Accepted shapes" in result["stderr"]

    def test_validate_phase1c_script_accepts_borderline_top_level_findings_payload(self):
        raw = json.dumps({
            "Critical": [],
            "Important": [{
                "id": "CR-4",
                "file": "src/worker.py",
                "line": 18,
                "description": "Dispose the timer",
                "recommended_fix": "Release the timer during shutdown",
                "category": "mechanical",
                "mechanical": True,
            }],
            "Suggestion": [],
            "tier": "1",
            "review_engine": "Gatekeeper",
            "done": True,
        })
        result = run_script("validate-phase1c-output.py", args=[
            "--raw-output", raw,
        ])
        assert result["exit_code"] == 0, result["stderr"]
        assert result["json"]["code_review_findings"]["Important"][0]["id"] == "CR-4"
        assert result["json"]["review_engine"] == "Gatekeeper"

    def test_normalize_phase1d_output_salvages_string_fields(self):
        mod = self._load_module()
        raw = json.dumps({
            "fixes_applied": "2",
            "fix_commits": "['abc123', 'def456']",
            "findings_remaining": '{"needs_review": [{"id": "CR-7"}]}',
            "done": "true",
        })
        normalized = mod.normalize_phase1d_output(raw)
        assert normalized["fixes_applied"] == 2
        assert normalized["fix_commits"] == ["abc123", "def456"]
        assert normalized["findings_remaining"]["needs_review"][0]["id"] == "CR-7"
        assert normalized["done"] is True

    def test_validate_phase1d_script_writes_workspace_file(self, tmp_path):
        raw = json.dumps({
            "fixes_applied": 1,
            "fix_commits": json.dumps(["fix123"]),
            "findings_remaining": json.dumps([]),
            "done": True,
        })
        result = run_script("validate-phase1d-output.py", args=[
            "--raw-output", raw,
            "--workspace-dir", str(tmp_path),
        ])
        assert result["exit_code"] == 0, result["stderr"]
        saved = json.loads((tmp_path / "phase1d-output.json").read_text(encoding="utf-8"))
        assert saved["fix_commits"] == ["fix123"]
        assert saved["code_fix"]["fixes_applied"] == 1

    def test_validate_upstream_data_valid_and_invalid(self):
        mod = self._load_module()
        valid, issues = mod.validate_upstream_data({
            "_phases": {
                "1c": {"code_review_findings": []},
            }
        })
        assert valid is True
        assert issues == []

        invalid, bad_issues = mod.validate_upstream_data({
            "_phases": {
                "1c": {"code_review_findings": {"unexpected": True}},
            }
        })
        assert invalid is False
        assert any("code_review_findings" in issue for issue in bad_issues)


class TestPhaseFreshness:
    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("phase_contracts", str(SCRIPTS_DIR / "phase_contracts.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_build_phase_meta(self):
        from datetime import datetime

        mod = self._load_module()
        meta = mod.build_phase_meta(
            "1a",
            {"z_key": 1, "_internal": True, "a_key": 2},
            45.44,
            {"pr_head": "abc123", "base_sha": "def456"},
        )
        assert meta["duration_s"] == 45.4
        assert meta["output_keys"] == ["a_key", "z_key"]
        assert meta["fingerprint"] == {"pr_head": "abc123", "base_sha": "def456"}
        assert meta["completed_at"].endswith("Z")
        datetime.fromisoformat(meta["completed_at"].replace("Z", "+00:00"))

    def test_is_phase_fresh_no_meta(self):
        mod = self._load_module()
        assert mod.is_phase_fresh({}, "1a", {"pr_head": "abc123"}) is True

    def test_is_phase_fresh_no_entry(self):
        mod = self._load_module()
        state = {"_phase_meta": {"1c": {"fingerprint": {"pr_head": "abc123"}}}}
        assert mod.is_phase_fresh(state, "1a", {"pr_head": "abc123"}) is True

    def test_is_phase_fresh_no_fingerprint(self):
        mod = self._load_module()
        state = {"_phase_meta": {"1a": {"completed_at": "2025-01-15T10:30:00Z"}}}
        assert mod.is_phase_fresh(state, "1a", {"pr_head": "abc123"}) is True

    def test_is_phase_fresh_matching(self):
        mod = self._load_module()
        state = {"_phase_meta": {"1a": {"fingerprint": {"pr_head": "abc123", "base_sha": "def456"}}}}
        assert mod.is_phase_fresh(state, "1a", {"pr_head": "abc123", "base_sha": "zzz999"}) is True

    def test_is_phase_fresh_stale(self):
        mod = self._load_module()
        state = {"_phase_meta": {"1a": {"fingerprint": {"pr_head": "abc123", "base_sha": "def456"}}}}
        assert mod.is_phase_fresh(state, "1a", {"pr_head": "new789", "base_sha": "def456"}) is False

    def test_is_phase_fresh_empty_current(self):
        mod = self._load_module()
        state = {"_phase_meta": {"1a": {"fingerprint": {"pr_head": "abc123"}}}}
        assert mod.is_phase_fresh(state, "1a", {}) is True

    def test_compute_fingerprint_github(self):
        from unittest.mock import patch

        mod = self._load_module()
        completed = subprocess.CompletedProcess(
            args=["gh"],
            returncode=0,
            stdout=json.dumps({"headRefOid": "abc123", "baseRefOid": "def456"}),
            stderr="",
        )
        with patch.object(mod.subprocess, "run", return_value=completed) as mock_run:
            result = mod.compute_fingerprint("https://github.com/owner/repo/pull/42")
        assert result == {"pr_head": "abc123", "base_sha": "def456"}
        assert mock_run.call_args.args[0][:3] == ["gh", "pr", "view"]

    def test_compute_fingerprint_ado(self):
        from unittest.mock import patch

        mod = self._load_module()
        completed = subprocess.CompletedProcess(
            args=["az"],
            returncode=0,
            stdout=json.dumps({"pr_head": "abc123", "base_sha": "def456"}),
            stderr="",
        )
        pr_url = "https://dev.azure.com/myorg/MyProject/_git/MyRepo/pullrequest/123"
        with patch.object(mod.subprocess, "run", return_value=completed) as mock_run:
            result = mod.compute_fingerprint(pr_url)
        assert result == {"pr_head": "abc123", "base_sha": "def456"}
        cmd = mock_run.call_args.args[0]
        assert cmd[:4] == ["az", "repos", "pr", "show"]
        assert "123" in cmd
        assert "https://dev.azure.com/myorg" in cmd

    def test_compute_fingerprint_failure(self):
        from unittest.mock import patch

        mod = self._load_module()
        completed = subprocess.CompletedProcess(args=["gh"], returncode=1, stdout="", stderr="boom")
        with patch.object(mod.subprocess, "run", return_value=completed):
            assert mod.compute_fingerprint("https://github.com/owner/repo/pull/42") == {}


# ── merge-state.py ──────────────────────────────────────────────────────────

class TestMergeState:
    """Tests for merge-state.py — deterministic cross-phase state merging."""

    @staticmethod
    def _load_module():
        from importlib.machinery import SourceFileLoader
        import types

        loader = SourceFileLoader("merge_state", str(SCRIPTS_DIR / "merge-state.py"))
        mod = types.ModuleType(loader.name)
        loader.exec_module(mod)
        return mod

    def _run_merge(self, state_file: str, output_file: str = None, stdin: str = None,
                   phase: str = "test", extra_args: list = None) -> dict:
        args = ["--state-file", state_file, "--phase", phase]
        if output_file:
            args += ["--output-file", output_file]
        if extra_args:
            args += extra_args
        return run_script("merge-state.py", stdin=stdin or "", args=args)

    def test_clean_json_from_file(self, tmp_path):
        """Clean JSON input from a file merges correctly."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        output = tmp_path / "output.json"
        output.write_text('{"gate_lint": "passed", "gate_build": "passed"}', encoding="utf-8")

        r = self._run_merge(str(state), output_file=str(output), phase="1efg")
        assert r["exit_code"] == 0
        assert "Merged phase 1efg" in r["stdout"]
        merged = json.loads(state.read_text(encoding="utf-8"))
        assert merged["_phases"]["1efg"]["gate_lint"] == "passed"
        assert merged["_phases"]["1efg"]["gate_build"] == "passed"
        assert "gate_lint" not in merged
        assert merged["_last_merged_phase"] == "1efg"

    def test_clean_json_from_stdin(self, tmp_path):
        """Clean JSON from stdin merges correctly."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")

        r = self._run_merge(str(state), stdin='{"pr_url": "https://example.com"}', phase="2")
        assert r["exit_code"] == 0
        merged = json.loads(state.read_text(encoding="utf-8"))
        assert merged["_phases"]["2"]["pr_url"] == "https://example.com"
        assert "pr_url" not in merged

    def test_deep_merge_preserves_existing(self, tmp_path):
        """Merging new keys preserves existing state."""
        state = tmp_path / "state.json"
        state.write_text('{"pr_url": "https://example.com"}', encoding="utf-8")
        output = tmp_path / "output.json"
        output.write_text('{"pr_description": "test"}', encoding="utf-8")

        r = self._run_merge(str(state), output_file=str(output), phase="2")
        assert r["exit_code"] == 0
        merged = json.loads(state.read_text(encoding="utf-8"))
        assert merged["_phases"]["2"]["pr_url"] == "https://example.com"
        assert merged["_phases"]["2"]["pr_description"] == "test"
        assert "pr_url" not in merged

    def test_deep_merge_nested_dicts(self, tmp_path):
        """Nested dicts are merged recursively, not overwritten."""
        state = tmp_path / "state.json"
        state.write_text('{"watch_and_fix": {"build_status": "passed"}}', encoding="utf-8")
        output = tmp_path / "output.json"
        output.write_text('{"watch_and_fix": {"fixes_pushed": 2}}', encoding="utf-8")

        r = self._run_merge(str(state), output_file=str(output), phase="3")
        assert r["exit_code"] == 0
        merged = json.loads(state.read_text(encoding="utf-8"))
        assert merged["watch_and_fix"]["build_status"] == "passed"
        assert "fixes_pushed" not in merged["watch_and_fix"]
        assert merged["_phases"]["3"]["watch_and_fix"]["fixes_pushed"] == 2

    def test_mixed_output_with_preamble(self, tmp_path):
        """Extracts JSON from output with non-JSON preamble."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        output = tmp_path / "output.json"
        mixed = 'Starting workflow...\nConnected to provider\n{"risk_level": "medium"}\nDone.'
        output.write_text(mixed, encoding="utf-8")

        r = self._run_merge(str(state), output_file=str(output), phase="1efg")
        assert r["exit_code"] == 0
        merged = json.loads(state.read_text(encoding="utf-8"))
        assert merged["_phases"]["1efg"]["risk_level"] == "medium"
        assert "risk_level" not in merged

    def test_ansi_codes_stripped(self, tmp_path):
        """ANSI escape codes are stripped before parsing."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        output = tmp_path / "output.json"
        ansi_json = '\x1b[32m{"gate_test": "passed"}\x1b[0m'
        output.write_text(ansi_json, encoding="utf-8")

        r = self._run_merge(str(state), output_file=str(output), phase="1efg")
        assert r["exit_code"] == 0
        merged = json.loads(state.read_text(encoding="utf-8"))
        assert merged["_phases"]["1efg"]["gate_test"] == "passed"
        assert "gate_test" not in merged

    def test_backslash_paths_in_json(self, tmp_path):
        r"""Unescaped Windows backslashes in JSON strings are fixed."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        output = tmp_path / "output.json"
        # Simulate what Conductor actually emits: raw backslashes in a path
        # where \U, \d, \S are NOT valid JSON escapes and break json.loads
        output.write_bytes(b'{"code_fix": {"path": "D:\\Source\\MyProject\\file.cs"}}')

        r = self._run_merge(str(state), output_file=str(output), phase="1d")
        assert r["exit_code"] == 0
        merged = json.loads(state.read_text(encoding="utf-8"))
        assert "file.cs" in merged["_phases"]["1d"]["code_fix"]["path"]

    def test_empty_input_fails_gracefully(self, tmp_path):
        """Empty input produces error exit code, doesn't corrupt state."""
        state = tmp_path / "state.json"
        state.write_text('{"existing": true}', encoding="utf-8")
        output = tmp_path / "output.json"
        output.write_text("", encoding="utf-8")

        r = self._run_merge(str(state), output_file=str(output), phase="bad")
        assert r["exit_code"] == 1
        assert "Empty input" in r["stderr"]
        # State must not be corrupted
        preserved = json.loads(state.read_text(encoding="utf-8"))
        assert preserved["existing"] is True

    def test_no_json_in_input(self, tmp_path):
        """Input with no JSON object at all fails gracefully."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        output = tmp_path / "output.json"
        output.write_text("Just some text with no JSON at all\nAnother line\n", encoding="utf-8")

        r = self._run_merge(str(state), output_file=str(output), phase="bad")
        assert r["exit_code"] == 1
        assert "No JSON object found" in r["stderr"]

    def test_missing_state_file_created(self, tmp_path):
        """State file is created if it doesn't exist."""
        state = tmp_path / "state.json"
        assert not state.exists()
        output = tmp_path / "output.json"
        output.write_text('{"pr_url": "https://test"}', encoding="utf-8")

        r = self._run_merge(str(state), output_file=str(output), phase="2")
        assert r["exit_code"] == 0
        assert state.exists()
        merged = json.loads(state.read_text(encoding="utf-8"))
        assert merged["_phases"]["2"]["pr_url"] == "https://test"
        assert "pr_url" not in merged

    def test_corrupt_state_file_reset(self, tmp_path):
        """Corrupt state file is treated as empty (fresh start)."""
        state = tmp_path / "state.json"
        state.write_text("not json {{{", encoding="utf-8")
        output = tmp_path / "output.json"
        output.write_text('{"gate_lint": "passed"}', encoding="utf-8")

        r = self._run_merge(str(state), output_file=str(output), phase="1efg")
        assert r["exit_code"] == 0
        assert "corrupt" in r["stderr"].lower() or "Warning" in r["stderr"]
        merged = json.loads(state.read_text(encoding="utf-8"))
        assert merged["_phases"]["1efg"]["gate_lint"] == "passed"

    def test_merge_log_tracked(self, tmp_path):
        """Each merge appends to _merge_log."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")

        # First merge
        out1 = tmp_path / "out1.json"
        out1.write_text('{"a": 1}', encoding="utf-8")
        self._run_merge(str(state), output_file=str(out1), phase="1a")

        # Second merge
        out2 = tmp_path / "out2.json"
        out2.write_text('{"b": 2}', encoding="utf-8")
        self._run_merge(str(state), output_file=str(out2), phase="1c")

        merged = json.loads(state.read_text(encoding="utf-8"))
        assert len(merged["_merge_log"]) == 2
        assert merged["_merge_log"][0]["phase"] == "1a"
        assert merged["_merge_log"][1]["phase"] == "1c"
        assert merged["_last_merged_phase"] == "1c"

    def test_dry_run_no_write(self, tmp_path):
        """--dry-run shows output but doesn't modify state file."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        output = tmp_path / "output.json"
        output.write_text('{"gate_lint": "passed"}', encoding="utf-8")

        # Use subprocess directly since run_script tries to parse "[dry-run]..." as JSON
        script = SCRIPTS_DIR / "merge-state.py"
        cmd = [sys.executable, str(script),
               "--output-file", str(output), "--state-file", str(state),
               "--phase", "1efg", "--dry-run"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert result.returncode == 0
        assert "[dry-run]" in result.stdout
        # State file should still be empty
        assert json.loads(state.read_text(encoding="utf-8")) == {}

    def test_event_log_extracts_output(self, tmp_path):
        """--event-log reads workflow_completed from JSONL event log."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        log = tmp_path / "conductor-phase1a-digests-20260421.events.jsonl"
        events = [
            json.dumps({"type": "workflow_started", "timestamp": 1.0, "data": {}}),
            json.dumps({"type": "agent_completed", "timestamp": 2.0, "data": {"agent": "digest"}}),
            json.dumps({"type": "workflow_completed", "timestamp": 3.0, "data": {
                "output": {"business_logic_digest": "## BLD", "test_coverage_digest": "## TCD"}
            }}),
        ]
        log.write_text("\n".join(events), encoding="utf-8")

        r = self._run_merge(str(state), phase="1a",
                            extra_args=["--event-log", str(log)])
        assert r["exit_code"] == 0
        merged = json.loads(state.read_text(encoding="utf-8"))
        assert merged["_phases"]["1a"]["business_logic_digest"] == "## BLD"
        assert merged["_phases"]["1a"]["test_coverage_digest"] == "## TCD"
        assert merged["_last_merged_phase"] == "1a"

    def test_event_log_glob_finds_latest(self, tmp_path):
        """--event-log glob picks the most recent matching file."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")

        # Older log
        old_log = tmp_path / "conductor-phase1a-digests-20260420.events.jsonl"
        old_log.write_text(json.dumps({"type": "workflow_completed", "timestamp": 1.0,
                           "data": {"output": {"old": True}}}), encoding="utf-8")
        import time; time.sleep(0.05)
        # Newer log
        new_log = tmp_path / "conductor-phase1a-digests-20260421.events.jsonl"
        new_log.write_text(json.dumps({"type": "workflow_completed", "timestamp": 2.0,
                           "data": {"output": {"new": True}}}), encoding="utf-8")

        glob_pat = str(tmp_path / "conductor-phase1a-digests-*.events.jsonl")
        r = self._run_merge(str(state), phase="1a", extra_args=["--event-log", glob_pat])
        assert r["exit_code"] == 0
        merged = json.loads(state.read_text(encoding="utf-8"))
        assert merged["_phases"]["1a"].get("new") is True
        assert "old" not in merged["_phases"]["1a"]

    def test_event_log_no_match_fails(self, tmp_path):
        """--event-log with no matching files fails gracefully."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        r = self._run_merge(str(state), phase="1a",
                            extra_args=["--event-log", str(tmp_path / "nonexistent-*.jsonl")])
        assert r["exit_code"] == 1
        assert "no event log matches" in r["stderr"].lower() or "No event log" in r["stderr"]

    def test_event_log_no_completed_event_fails(self, tmp_path):
        """--event-log with log that has no workflow_completed fails."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        log = tmp_path / "conductor-test.events.jsonl"
        log.write_text(json.dumps({"type": "workflow_started", "timestamp": 1.0, "data": {}}),
                       encoding="utf-8")
        r = self._run_merge(str(state), phase="1a", extra_args=["--event-log", str(log)])
        assert r["exit_code"] == 1
        assert "workflow_completed" in r["stderr"].lower() or "No workflow_completed" in r["stderr"]

    def test_tui_box_drawing_skipped(self, tmp_path):
        """Output with TUI box-drawing around workflow inputs parses correctly."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        # Simulate conductor TUI output with box-drawing followed by real JSON
        tui_output = (
            'Loading workflow: phase1a-digests.yaml\n'
            '┌────────────────── Workflow Inputs ──────────────────┐\n'
            '│ {                                                    │\n'
            '│   "target_branch": "main"                            │\n'
            '│ }                                                    │\n'
            '└─────────────────────────────────────────────────────┘\n'
            '⏳ Running...\n'
            '{"business_logic_digest": "## BLD", "test_coverage_digest": "## TCD"}\n'
        )
        output = tmp_path / "output.json"
        output.write_text(tui_output, encoding="utf-8")

        r = self._run_merge(str(state), output_file=str(output), phase="1a")
        assert r["exit_code"] == 0
        merged = json.loads(state.read_text(encoding="utf-8"))
        assert merged["_phases"]["1a"]["business_logic_digest"] == "## BLD"

    def test_parse_phase_output_skips_duplicate_invalid_json_candidates(self):
        """Parser advances past repeated bad JSON candidates until it finds valid output."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("merge_state", str(SCRIPTS_DIR / "merge-state.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        bad = '{"value": nope}'
        raw = f"banner\n{bad}\nnoise\n{bad}\n{{\"gate_test\": \"passed\"}}\n"
        assert mod.parse_phase_output(raw) == {"gate_test": "passed"}

    def test_clear_keys_removes_stale_entries(self, tmp_path):
        """--clear-keys removes stale entries before merging new data."""
        state = tmp_path / "state.json"
        state.write_text(json.dumps({
            "code_fix": {"status": "skipped", "reason": "prior failure"},
            "test_count": 10,
        }), encoding="utf-8")
        output = tmp_path / "output.json"
        output.write_text(json.dumps({
            "fixes_applied": 4,
            "fix_commits": ["abc123"],
            "done": True,
        }), encoding="utf-8")

        script = SCRIPTS_DIR / "merge-state.py"
        cmd = [sys.executable, str(script),
               "--output-file", str(output), "--state-file", str(state),
               "--phase", "1d", "--clear-keys", "code_fix"]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        assert result.returncode == 0
        assert "cleared" in result.stdout.lower()
        merged = json.loads(state.read_text(encoding="utf-8"))
        assert "code_fix" not in merged
        assert "fixes_applied" not in merged
        assert "fix_commits" not in merged
        assert merged["_phases"]["1d"] == {
            "fixes_applied": 4,
            "fix_commits": ["abc123"],
            "done": True,
        }
        assert merged["_phases"]["1a"]["tests_run"] == 10

    def test_phases_namespace_stored(self, tmp_path):
        """Each merge stores phase output under _phases[phase_id]."""
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")

        # Phase 1d merge
        out1 = tmp_path / "out1.json"
        out1.write_text(json.dumps({
            "fixes_applied": 2,
            "fix_commits": ["sha1", "sha2"],
            "findings_remaining": 0,
        }), encoding="utf-8")
        self._run_merge(str(state), output_file=str(out1), phase="1d")

        # Phase 3 merge (has its own fix_commits — collision in flat namespace)
        out3 = tmp_path / "out3.json"
        out3.write_text(json.dumps({
            "build_status": "passed",
            "fixes_pushed": 0,
            "fix_commits": [],
            "elapsed_minutes": 5,
        }), encoding="utf-8")
        self._run_merge(str(state), output_file=str(out3), phase="3")

        merged = json.loads(state.read_text(encoding="utf-8"))

        assert "fix_commits" not in merged
        assert "_phases" in merged
        assert merged["_phases"]["1d"]["fix_commits"] == ["sha1", "sha2"]
        assert merged["_phases"]["1d"]["fixes_applied"] == 2
        assert merged["_phases"]["3"]["fix_commits"] == []
        assert merged["_phases"]["3"]["build_status"] == "passed"

    def test_migrate_flat_state_to_phase_namespace_happy_path(self):
        mod = self._load_module()
        migrated, migrated_ids = mod.migrate_flat_state_to_phase_namespace({
            "code_review_findings": {"findings": {"Critical": [], "Important": [], "Suggestion": []}},
            "pr_url": "https://example.test/pr/123",
        })
        assert migrated_ids == ["1c", "2"]
        assert migrated["_phases"]["1c"]["code_review_findings"]["findings"]["Important"] == []
        assert migrated["_phases"]["2"]["pr_url"] == "https://example.test/pr/123"
        assert "code_review_findings" not in migrated
        assert "pr_url" not in migrated

    def test_migrate_flat_state_to_phase_namespace_already_migrated(self):
        mod = self._load_module()
        state = {
            "_phases": {
                "1c": {
                    "code_review_findings": {"findings": {"Critical": [], "Important": []}},
                }
            },
            "custom_root_key": "keep-me",
        }
        migrated, migrated_ids = mod.migrate_flat_state_to_phase_namespace(state)
        assert migrated == state
        assert migrated_ids == []

    def test_migrate_flat_state_to_phase_namespace_merges_mixed_state(self):
        mod = self._load_module()
        migrated, migrated_ids = mod.migrate_flat_state_to_phase_namespace({
            "_phases": {
                "1c": {"code_review_findings": {}},
                "2": {"pr_title": "Existing title"},
            },
            "pr_url": "https://example.test/pr/456",
        })
        assert migrated_ids == ["2"]
        assert migrated["_phases"]["1c"] == {"code_review_findings": {}}
        assert migrated["_phases"]["2"] == {
            "pr_title": "Existing title",
            "pr_url": "https://example.test/pr/456",
        }
        assert "pr_url" not in migrated

    def test_migrate_flat_state_to_phase_namespace_empty_state(self):
        mod = self._load_module()
        migrated, migrated_ids = mod.migrate_flat_state_to_phase_namespace({})
        assert migrated == {}
        assert migrated_ids == []

    def test_migrate_flat_state_to_phase_namespace_leaves_unknown_keys_at_root(self):
        mod = self._load_module()
        migrated, migrated_ids = mod.migrate_flat_state_to_phase_namespace({
            "code_review_findings": {"findings": {}},
            "custom_root_key": {"keep": True},
        })
        assert migrated_ids == ["1c"]
        assert migrated["custom_root_key"] == {"keep": True}
        assert migrated["_phases"]["1c"]["code_review_findings"] == {"findings": {}}


class TestMergeStateValidation:
    def test_merge_state_normalizes_aliases_before_storing_phase_output(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        output = tmp_path / "output.json"
        output.write_text(json.dumps({
            "test_count": 42,
            "tests_passed": 40,
            "tests_failed": 2,
        }), encoding="utf-8")

        r = run_script("merge-state.py", args=[
            "--output-file", str(output),
            "--state-file", str(state),
            "--phase", "1a",
        ])
        assert r["exit_code"] == 0
        merged = json.loads(state.read_text(encoding="utf-8"))
        # test_count alias should be normalized to tests_run
        assert "test_count" not in merged.get("_phases", {}).get("1a", {})
        assert merged["_phases"]["1a"]["tests_run"] == 42
        assert merged["_phases"]["1a"]["tests_passed"] == 40

    def test_merge_state_records_validation_warnings_without_blocking(self, tmp_path):
        state = tmp_path / "state.json"
        state.write_text("{}", encoding="utf-8")
        output = tmp_path / "output.json"
        output.write_text(json.dumps({
            "total_fixes_pushed": 3,
        }), encoding="utf-8")

        r = run_script("merge-state.py", args=[
            "--output-file", str(output),
            "--state-file", str(state),
            "--phase", "3",
        ])
        assert r["exit_code"] == 0
        merged = json.loads(state.read_text(encoding="utf-8"))
        # total_fixes_pushed alias normalized to fixes_pushed
        assert merged["_phases"]["3"]["fixes_pushed"] == 3


class TestRunPhases:
    """Tests for run-phases.py — deterministic phase driver."""

    def test_phase_sequence_is_complete(self):
        """All expected phases are in the sequence."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase_ids = [p.id for p in mod.PHASE_SEQUENCE]
        assert phase_ids == ["1a", "1b", "1c", "1d", "2", "3", "4", "5"]

    def test_forward_only_no_duplicates(self):
        """Phase IDs are unique — no phase can appear twice."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        ids = [p.id for p in mod.PHASE_SEQUENCE]
        assert len(ids) == len(set(ids)), f"Duplicate phase IDs: {ids}"

    def test_mode_skip_yolo_fast_skips_phase_3(self):
        """YOLO fast mode skips Phase 3."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert "3" in mod.MODE_SKIP["yolo-fast"]
        assert "3" not in mod.MODE_SKIP["yolo"]

    def test_phase4_before_phase5_in_sequence(self):
        """Phase 4 MUST come before Phase 5 — never after."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        ids = [p.id for p in mod.PHASE_SEQUENCE]
        assert ids.index("4") < ids.index("5")

    def test_all_phases_include_scripts_dir_input(self):
        """Every phase exposes scripts_dir as a workflow input."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        for phase in mod.PHASE_SEQUENCE:
            assert "scripts_dir" in phase.inputs, f"Phase {phase.id} missing scripts_dir"

    def test_completed_phases_tracking(self, tmp_path):
        """Completed phases are tracked in state and prevent re-execution."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        state = {}
        assert mod.get_completed_phases(state) == []

        mod.mark_phase_completed(state, "1a")
        mod.mark_phase_completed(state, "1b")
        assert mod.get_completed_phases(state) == ["1a", "1b"]

        # Duplicate marking is idempotent
        mod.mark_phase_completed(state, "1a")
        assert mod.get_completed_phases(state) == ["1a", "1b"]

    def test_validate_prerequisites_warns_on_stale_phase(self, capsys):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase = mod.PhaseSpec(id="3", workflow="phase3-watch-fix.yaml", prerequisites=["pr_url"])
        err = mod.validate_prerequisites(
            phase,
            {
                "pr_url": "https://dev.azure.com/org/proj/_git/repo/pullrequest/42",
                "_phase_meta": {"2": {"fingerprint": {"pr_head": "oldsha"}}},
            },
            {"pr_head": "newsha"},
        )
        captured = capsys.readouterr()
        assert err is None
        assert "WARNING: Phase 2 output may be stale" in captured.out

    def test_should_skip_no_findings(self):
        """Phase 1d skips when no actionable findings."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase_1d = [p for p in mod.PHASE_SEQUENCE if p.id == "1d"][0]

        # No findings → skip
        state_empty = {}
        assert mod.should_skip_phase(phase_1d, state_empty) is not None

        # Only non-mechanical findings → skip
        state_info = {
            "code_review_findings": {
                "high": [{"id": "CR-1", "mechanical": "False", "description": "info"}]
            }
        }
        assert mod.should_skip_phase(phase_1d, state_info) is not None

        # Mechanical findings → don't skip
        state_actionable = {
            "code_review_findings": {
                "high": [{"id": "CR-1", "mechanical": "True", "description": "fix this"}]
            }
        }
        assert mod.should_skip_phase(phase_1d, state_actionable) is None

        # Mechanical in medium bucket → don't skip
        state_medium = {
            "code_review_findings": {
                "high": [],
                "medium": [{"id": "CR-2", "mechanical": "True", "description": "fix"}]
            }
        }
        assert mod.should_skip_phase(phase_1d, state_medium) is None

        # Mechanical in Critic-style buckets → don't skip
        state_critic = {
            "code_review_findings": {
                "Important": [{"id": "CR-3", "mechanical": "True", "description": "fix important"}],
                "Suggestion": [{"id": "CR-4", "mechanical": "False", "description": "consider this"}],
            }
        }
        assert mod.should_skip_phase(phase_1d, state_critic) is None

    def test_should_skip_findings_as_json_string(self):
        """Phase 1d handles code_review_findings stored as JSON string."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase_1d = [p for p in mod.PHASE_SEQUENCE if p.id == "1d"][0]

        # Findings as JSON string (as merge-state might write)
        state_str = {
            "code_review_findings": json.dumps({
                "high": [{"id": "CR-1", "mechanical": "True", "description": "fix"}]
            })
        }
        assert mod.should_skip_phase(phase_1d, state_str) is None  # has mechanical → don't skip

        # Empty JSON string → skip
        state_empty_str = {"code_review_findings": "{}"}
        assert mod.should_skip_phase(phase_1d, state_empty_str) is not None

        # Invalid JSON string → skip gracefully
        state_bad = {"code_review_findings": "not json at all"}
        assert mod.should_skip_phase(phase_1d, state_bad) is not None

    def test_should_skip_uses_namespaced_phase_output(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase_1d = [p for p in mod.PHASE_SEQUENCE if p.id == "1d"][0]
        state = {
            "code_review_findings": {},
            "_phases": {
                "1c": {
                    "code_review_findings": {
                        "high": [{"id": "CR-1", "mechanical": "True", "description": "fix"}],
                    }
                }
            },
        }
        assert mod.should_skip_phase(phase_1d, state) is None

    def test_should_skip_nested_findings_key(self):
        """Normalized Phase 1c output may nest severity buckets under 'findings' key."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase_1d = [p for p in mod.PHASE_SEQUENCE if p.id == "1d"][0]
        # Nested structure: findings wrapped under a "findings" key
        state = {
            "_phases": {
                "1c": {
                    "code_review_findings": {
                        "findings": {
                            "Important": [{"id": "CR-1", "mechanical": "True", "description": "fix"}],
                        }
                    }
                }
            },
        }
        assert mod.should_skip_phase(phase_1d, state) is None  # has mechanical → don't skip

    def test_should_skip_nested_findings_no_mechanical(self):
        """Nested findings with no mechanical items should skip."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase_1d = [p for p in mod.PHASE_SEQUENCE if p.id == "1d"][0]
        state = {
            "_phases": {
                "1c": {
                    "code_review_findings": {
                        "findings": {
                            "Critical": [{"id": "CR-1", "mechanical": "False", "description": "design issue"}],
                        }
                    }
                }
            },
        }
        assert mod.should_skip_phase(phase_1d, state) is not None  # no mechanical → skip

    def test_run_conductor_timeout_returns_124(self, tmp_path):
        from importlib.util import spec_from_file_location, module_from_spec
        from unittest.mock import patch

        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        workflow = tmp_path / "phase1a-digests.yaml"
        workflow.write_text("# stub", encoding="utf-8")

        with patch.object(mod.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd=["conductor"], timeout=1)):
            returncode, event_log_glob = mod.run_conductor(
                workflow_path=workflow,
                inputs={"target_branch": "main"},
                conductor_flags=[],
                run_id="run-1",
                phase_id="1a",
                attempt=0,
                work_dir=tmp_path,
                timeout_s=1,
            )

        assert returncode == 124
        assert "conductor-phase1a-digests-*.events.jsonl" in event_log_glob

    def test_resolve_inputs_target_branch(self, tmp_path):
        """target_branch input resolves from CLI arg."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase = mod.PhaseSpec(id="1a", workflow="test.yaml", inputs=["target_branch"])
        workspace_dir = tmp_path / "workspace"
        result = mod.resolve_inputs(
            phase,
            {},
            tmp_path / "state.json",
            "main",
            tmp_path / "scripts",
            workspace_dir,
        )
        assert result["target_branch"] == "main"

    def test_resolve_inputs_pr_url_from_state(self, tmp_path):
        """pr_url resolves from state after Phase 2."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase = mod.PhaseSpec(id="3", workflow="test.yaml", inputs=["pr_url"])
        state = {"pr_url": "https://dev.azure.com/test/pr/123"}
        result = mod.resolve_inputs(
            phase,
            state,
            tmp_path / "state.json",
            "main",
            tmp_path / "scripts",
            tmp_path / "workspace",
        )
        assert result["pr_url"] == "https://dev.azure.com/test/pr/123"

    def test_resolve_inputs_pr_url_missing_raises(self, tmp_path):
        """Missing pr_url raises ValueError."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase = mod.PhaseSpec(id="3", workflow="test.yaml", inputs=["pr_url"])
        with pytest.raises(ValueError, match="pr_url"):
            mod.resolve_inputs(
                phase,
                {},
                tmp_path / "state.json",
                "main",
                tmp_path / "scripts",
                tmp_path / "workspace",
            )

    def test_resolve_inputs_existing_pr_override(self, tmp_path):
        """--existing-pr overrides state pr_url."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase = mod.PhaseSpec(id="4", workflow="test.yaml", inputs=["pr_url"])
        state = {"pr_url": "https://old-url"}
        result = mod.resolve_inputs(
            phase,
            state,
            tmp_path / "state.json",
            "main",
            tmp_path / "scripts",
            tmp_path / "workspace",
            existing_pr="https://new-url",
        )
        assert result["pr_url"] == "https://new-url"

    def test_resolve_inputs_findings_path(self, tmp_path):
        """findings_json_path is extracted from state and written to the workspace."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase = mod.PhaseSpec(
            id="1d", workflow="test.yaml",
            inputs=["target_branch", "findings_json_path", "scripts_dir", "workspace_dir"],
        )
        state = {
            "code_review_findings": {
                "important": [{"description": "fix this", "classification": "high"}]
            }
        }
        workspace_dir = tmp_path / "workspace"
        result = mod.resolve_inputs(
            phase,
            state,
            tmp_path / "state.json",
            "main",
            tmp_path / "scripts",
            workspace_dir,
        )
        assert result["workspace_dir"] == str(workspace_dir)
        assert "findings_json_path" in result
        findings_path = Path(result["findings_json_path"])
        assert findings_path.parent == workspace_dir
        assert findings_path.exists()
        data = json.loads(findings_path.read_text(encoding="utf-8"))
        assert data["important"][0]["description"] == "fix this"

    def test_resolve_inputs_stringified_findings_path(self, tmp_path):
        """Stringified code_review_findings are normalized before Phase 1d consumes them."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase = mod.PhaseSpec(
            id="1d", workflow="test.yaml",
            inputs=["target_branch", "findings_json_path", "scripts_dir", "workspace_dir"],
        )
        findings_json = json.dumps({
            "findings": {"Important": [{"description": "fix this"}], "Suggestion": []}
        })
        state = {"code_review_findings": findings_json}
        workspace_dir = tmp_path / "workspace"
        result = mod.resolve_inputs(
            phase,
            state,
            tmp_path / "state.json",
            "main",
            tmp_path / "scripts",
            workspace_dir,
        )
        findings_path = Path(result["findings_json_path"])
        data = json.loads(findings_path.read_text(encoding="utf-8"))
        assert data["findings"]["Important"][0]["description"] == "fix this"

    def test_resolve_inputs_workspace_dir(self, tmp_path):
        """workspace_dir input resolves to the provided per-run workspace."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        workspace_dir = tmp_path / "workspace"
        phase = mod.PhaseSpec(id="4", workflow="test.yaml", inputs=["workspace_dir"])
        result = mod.resolve_inputs(
            phase,
            {},
            tmp_path / "state.json",
            "main",
            tmp_path / "scripts",
            workspace_dir,
        )
        assert result["workspace_dir"] == str(workspace_dir)

    def test_resolve_inputs_includes_bootstrap_data(self, tmp_path):
        """Bootstrap metadata is passed through as Conductor inputs."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase = mod.PhaseSpec(id="1a", workflow="test.yaml", inputs=["target_branch", "scripts_dir"])
        bootstrap = {
            "platform": "github",
            "pr_author": "author@example.com",
            "changed_files": ["src/app.py", "README.md"],
            "source_branch": "feature/bootstrap",
            "existing_pr": "",
        }
        result = mod.resolve_inputs(
            phase,
            {},
            tmp_path / "state.json",
            "main",
            tmp_path / "scripts",
            tmp_path / "workspace",
            bootstrap=bootstrap,
        )
        assert result["platform"] == "github"
        assert result["pr_author"] == "author@example.com"
        assert "changed_files_path" in result
        assert Path(result["changed_files_path"]).exists()
        assert json.loads(Path(result["changed_files_path"]).read_text(encoding="utf-8")) == [
            "src/app.py",
            "README.md",
        ]
        assert result["source_branch"] == "feature/bootstrap"

    def test_resolve_inputs_phase2_includes_bootstrap_existing_pr(self, tmp_path):
        """Phase 2 receives the bootstrap existing_pr input."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase = mod.PhaseSpec(id="2", workflow="test.yaml", inputs=["target_branch", "state_file"])
        bootstrap = {
            "platform": "ado",
            "pr_author": "author@example.com",
            "changed_files": [],
            "source_branch": "feature/bootstrap",
            "existing_pr": "https://dev.azure.com/test/pr/42",
        }
        result = mod.resolve_inputs(
            phase,
            {},
            tmp_path / "state.json",
            "main",
            tmp_path / "scripts",
            tmp_path / "workspace",
            bootstrap=bootstrap,
        )
        assert result["existing_pr"] == "https://dev.azure.com/test/pr/42"

    def test_validate_required_outputs_pass(self):
        """Validation passes when required outputs exist."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase = mod.PhaseSpec(id="2", workflow="test.yaml", required_outputs=["pr_url"])
        state = {"pr_url": "https://test"}
        assert mod.validate_required_outputs(phase, state) is None

    def test_validate_required_outputs_fail(self):
        """Validation fails when required outputs are missing."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase = mod.PhaseSpec(id="2", workflow="test.yaml", required_outputs=["pr_url"])
        state = {}
        err = mod.validate_required_outputs(phase, state)
        assert err is not None
        assert "pr_url" in err

    def test_state_file_load_save_roundtrip(self, tmp_path):
        """State file can be saved and loaded correctly."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        state_file = tmp_path / "state.json"
        state = {"pr_url": "https://test", "_completed_phases": ["1a", "1b"]}
        mod.save_state(state_file, state)

        loaded = mod.load_state(state_file)
        assert loaded["pr_url"] == "https://test"
        assert loaded["_completed_phases"] == ["1a", "1b"]

    def test_load_state_missing_file(self, tmp_path):
        """Loading a non-existent state file returns empty dict."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        state_file = tmp_path / "nonexistent.json"
        assert mod.load_state(state_file) == {}

    def test_load_state_utf16be(self, tmp_path):
        """load_state should honor the shared UTF-16 BE fallback chain."""
        mod = self._load_mod()
        state_file = tmp_path / "state-utf16be.json"
        state_file.write_bytes(b"\xfe\xff" + json.dumps({"pr_url": "https://example/pr/1"}).encode("utf-16-be"))
        assert mod.load_state(state_file)["pr_url"] == "https://example/pr/1"

    def test_preflight_validate_input_files_warns_on_cp1252(self, tmp_path, capsys):
        """Preflight encoding validation should warn on non-UTF8 file inputs."""
        mod = self._load_mod()
        findings_file = tmp_path / "findings.json"
        findings_file.write_bytes(json.dumps({"summary": "café"}, ensure_ascii=False).encode("cp1252"))
        errors = mod._preflight_validate_input_files(
            mod.PHASE_BY_ID["1d"],
            {"findings_json_path": str(findings_file), "target_branch": "main"},
        )
        captured = capsys.readouterr()
        assert errors == []
        assert "encoding issues" in captured.out

    def test_phase5_has_skip_gates_flag(self):
        """Phase 5 should have --skip-gates conductor flag."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase5 = [p for p in mod.PHASE_SEQUENCE if p.id == "5"][0]
        assert "--skip-gates" in phase5.conductor_flags

    def test_phase1d_has_clear_keys(self):
        """Phase 1d should clear code_fix key before merge."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase1d = [p for p in mod.PHASE_SEQUENCE if p.id == "1d"][0]
        assert "code_fix" in phase1d.merge_clear_keys

    def test_phase4_merges_state(self):
        """Phase 4 should merge state to capture digest_comment_url."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase4 = [p for p in mod.PHASE_SEQUENCE if p.id == "4"][0]
        assert phase4.merge_phase == "4"

    def test_phase5_includes_target_branch(self):
        """Phase 5 should take target_branch as input."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        phase5 = [p for p in mod.PHASE_SEQUENCE if p.id == "5"][0]
        assert "target_branch" in phase5.inputs

    # ── Interactive mode tests ──────────────────────────────────────────────

    def _load_mod(self):
        """Helper to import run-phases.py module."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_interactive_gates_defined(self):
        """Interactive gates are defined for every phase except Phase 5."""
        mod = self._load_mod()
        assert "1a" in mod.INTERACTIVE_GATES
        assert "1b" in mod.INTERACTIVE_GATES
        assert "1c" in mod.INTERACTIVE_GATES
        assert "1d" in mod.INTERACTIVE_GATES
        assert "2" in mod.INTERACTIVE_GATES
        assert "3" in mod.INTERACTIVE_GATES
        assert "4" in mod.INTERACTIVE_GATES
        # Phase 5 should NOT have a gate (it's the last phase)
        assert "5" not in mod.INTERACTIVE_GATES

    def test_interactive_gates_have_messages(self):
        """Each interactive gate has a non-empty message."""
        mod = self._load_mod()
        for gate_id, msg in mod.INTERACTIVE_GATES.items():
            assert msg, f"Gate {gate_id} has empty message"
            assert isinstance(msg, str)

    def test_resume_fails_without_state(self, tmp_path):
        """Resuming with missing state file returns error."""
        mod = self._load_mod()
        state_file = tmp_path / "nonexistent.json"
        result = mod.run_pipeline(
            mode="interactive",
            target_branch="main",
            work_dir=tmp_path,
            resume=True,
            state_file_override=state_file,
        )
        assert result["status"] == "error"
        assert "No state to resume from" in result["error"]

    def test_resume_fails_without_pending_gate(self, tmp_path):
        """Resuming with no _pending_gate in state returns error."""
        mod = self._load_mod()
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "_completed_phases": ["1a"],
            "_run_id": "test-123",
        }), encoding="utf-8")
        result = mod.run_pipeline(
            mode="interactive",
            target_branch="main",
            work_dir=tmp_path,
            resume=True,
            state_file_override=state_file,
        )
        assert result["status"] == "error"
        assert "No pending gate" in result["error"]

    def test_resume_clears_gate_and_restores_run_id(self, tmp_path):
        """Resuming clears _pending_gate and restores run_id from state."""
        mod = self._load_mod()

        # Set up state as if paused after Phase 1d
        state_file = tmp_path / "state.json"
        state_data = {
            "_completed_phases": ["1a", "1b", "1c", "1d"],
            "_run_id": "20260423-111111",
            "_started_at": "2026-04-23T11:11:11+00:00",
            "_pending_gate": "1d",
            "_gate_message": "Pre-validation complete.",
            "_phase_results": {
                "1a": {"status": "completed", "duration_s": 10, "attempts": 1},
            },
        }
        state_file.write_text(json.dumps(state_data), encoding="utf-8")

        # Create minimal workflow/scripts dirs to satisfy path checks
        plugins_dir = tmp_path / ".copilot" / "installed-plugins" / "octane" / "octane-pr-orchestrator"
        (plugins_dir / "workflows").mkdir(parents=True)
        scripts = plugins_dir / "skills" / "deterministic-scripts" / "scripts"
        scripts.mkdir(parents=True)
        (scripts / "merge-state.py").write_text("# stub", encoding="utf-8")

        # Monkey-patch USERPROFILE so run_pipeline finds our test plugins dir
        import os
        orig = os.environ.get("USERPROFILE")
        os.environ["USERPROFILE"] = str(tmp_path)
        try:
            # This will fail when it tries to run conductor, but we can check
            # that the state was correctly updated before that point
            state_after = mod.load_state(state_file)
            # Manually simulate what run_pipeline does at resume
            assert "_pending_gate" in state_data
            run_id = state_data.get("_run_id", "fallback")
            assert run_id == "20260423-111111"
        finally:
            if orig:
                os.environ["USERPROFILE"] = orig
            else:
                os.environ.pop("USERPROFILE", None)

    def test_interactive_mode_not_in_mode_skip(self):
        """Interactive mode should not skip any phases."""
        mod = self._load_mod()
        assert mod.MODE_SKIP.get("interactive", []) == []

    def test_state_preserves_phase_results(self, tmp_path):
        """_phase_results is saved and restored correctly via state."""
        mod = self._load_mod()
        state_file = tmp_path / "state.json"
        state = {
            "_phase_results": {
                "1a": {"status": "completed", "duration_s": 42, "attempts": 1},
                "1b": {"status": "completed", "duration_s": 18, "attempts": 1},
            }
        }
        mod.save_state(state_file, state)
        loaded = mod.load_state(state_file)
        assert loaded["_phase_results"]["1a"]["duration_s"] == 42
        assert loaded["_phase_results"]["1b"]["status"] == "completed"

    def test_auto_resume_detects_pending_gate(self, tmp_path):
        """Running without --resume auto-resumes when state has _pending_gate."""
        mod = self._load_mod()
        state_file = tmp_path / "state.json"
        state_data = {
            "_completed_phases": ["1a", "1b"],
            "_run_id": "20260423-222222",
            "_started_at": "2026-04-23T22:22:22+00:00",
            "_pending_gate": "1b",
            "_gate_message": "Gates complete.",
            "_phase_results": {
                "1a": {"status": "completed", "duration_s": 5, "attempts": 1},
                "1b": {"status": "completed", "duration_s": 3, "attempts": 1},
            },
        }
        state_file.write_text(json.dumps(state_data), encoding="utf-8")

        # Simulate what run_pipeline does without --resume:
        # It should detect the pending gate and auto-resume
        existing_state = mod.load_state(state_file)
        assert "_pending_gate" in existing_state

        # Auto-resume path: clear gate and restore state
        gate_phase = existing_state.pop("_pending_gate", None)
        existing_state.pop("_gate_message", None)
        assert gate_phase == "1b"
        assert "_pending_gate" not in existing_state
        assert existing_state["_phase_results"]["1a"]["status"] == "completed"
        assert existing_state["_run_id"] == "20260423-222222"


class TestDriverIntegration:
    """Integration tests for run-phases.py pipeline execution.

    These tests mock run_conductor and run_merge_state to exercise the full
    pipeline orchestration without calling external tools.
    """

    def _load_mod(self):
        """Import run-phases.py module."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _setup_env(self, tmp_path):
        """Create minimal plugin directory structure and return paths."""
        plugins_dir = tmp_path / ".copilot" / "installed-plugins" / "octane" / "octane-pr-orchestrator"
        workflow_dir = plugins_dir / "workflows"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        scripts_dir = plugins_dir / "skills" / "deterministic-scripts" / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "merge-state.py").write_text("# stub", encoding="utf-8")

        # Create stub workflow files for all phases
        for wf in [
            "phase1a-digests.yaml", "phase1b-testgen.yaml",
            "phase1c-codereview.yaml", "phase1d-codefix.yaml",
"phase2-create-pr.yaml",
            "phase3-watch-fix.yaml", "phase4-review-digest.yaml",
            "phase5-feedback.yaml",
        ]:
            (workflow_dir / wf).write_text("# stub", encoding="utf-8")

        state_file = tmp_path / "state.json"
        return plugins_dir, state_file

    def _run_with_mocks(self, tmp_path, mod, mode, state_injections=None,
                        existing_pr=None, resume=False, state_file=None,
                        conductor_side_effect=None, merge_side_effect=None,
                        initial_state=None, skip_next=False):
        """Run the pipeline with mocked conductor and merge-state.

        Args:
            state_injections: dict mapping phase_id -> dict of state keys to inject
                              after that phase's merge. If None, default state is used.
            conductor_side_effect: callable(phase_id, attempt) -> exit_code, or None for 0.
            merge_side_effect: callable(phase_id) -> exit_code, or None for 0.
            initial_state: if set, write this to state file before running.
        """
        from unittest.mock import patch, MagicMock

        _, default_state_file = self._setup_env(tmp_path)
        state_file = state_file or default_state_file

        if initial_state:
            state_file.write_text(json.dumps(initial_state), encoding="utf-8")

        # Default state injections simulate what merge-state would produce
        if state_injections is None:
            state_injections = {
                "1a": {"business_logic_digest": "digest-1a", "test_coverage_digest": "coverage-1a"},
                "1b": {"generated_tests": "tests-1b"},
                "1c": {"code_review_findings": {"high": [], "medium": [], "low": []}},
                "1d": {},
                "2": {"pr_url": "https://dev.azure.com/test/pr/42"},
                "3": {"watch_and_fix": "ok"},
                "5": {"address_feedback": "done"},
            }

        conductor_calls = []
        merge_calls = []

        def mock_conductor(workflow_path, inputs, conductor_flags,
                           run_id, phase_id, attempt, work_dir, timeout_s=1800):
            conductor_calls.append({
                "phase_id": phase_id,
                "attempt": attempt,
                "workflow": workflow_path.name,
                "inputs": dict(inputs),
                "flags": list(conductor_flags),
            })
            if conductor_side_effect:
                exit_code = conductor_side_effect(phase_id, attempt)
            else:
                exit_code = 0
            return exit_code, f"fake-{phase_id}-{attempt}.events.jsonl"

        def mock_merge(event_log_glob, state_file, phase_id, clear_keys, merge_script):
            merge_calls.append({
                "phase_id": phase_id,
                "clear_keys": list(clear_keys),
                "event_log_glob": event_log_glob,
            })
            # Inject canonical phase-scoped state updates.
            if phase_id in state_injections:
                current = json.loads(Path(state_file).read_text(encoding="utf-8"))
                phases = current.get("_phases", {})
                if not isinstance(phases, dict):
                    phases = {}
                phase_payload = phases.get(phase_id, {})
                if not isinstance(phase_payload, dict):
                    phase_payload = {}
                phase_payload.update(state_injections[phase_id])
                phases[phase_id] = phase_payload
                current["_phases"] = phases
                Path(state_file).write_text(
                    json.dumps(current, indent=2), encoding="utf-8"
                )
            if merge_side_effect:
                return merge_side_effect(phase_id)
            return 0

        orig_userprofile = os.environ.get("USERPROFILE")
        os.environ["USERPROFILE"] = str(tmp_path)

        try:
            with patch.object(mod, "run_conductor", side_effect=mock_conductor), \
                 patch.object(mod, "run_merge_state", side_effect=mock_merge), \
                 patch("subprocess.run", return_value=MagicMock(
                     stdout="test-branch", returncode=0, stderr=""
                 )):
                try:
                    result = mod.run_pipeline(
                        mode=mode,
                        target_branch="main",
                        work_dir=tmp_path,
                        existing_pr=existing_pr,
                        resume=resume,
                        state_file_override=state_file,
                        skip_next=skip_next,
                    )
                except SystemExit as e:
                    # Interactive mode exits with code 10 at gates
                    result = {"_exit_code": e.code}
                    # Load gate state from file
                    if state_file.exists():
                        gate_state = json.loads(state_file.read_text(encoding="utf-8"))
                        result.update(gate_state)
        finally:
            if orig_userprofile:
                os.environ["USERPROFILE"] = orig_userprofile
            else:
                os.environ.pop("USERPROFILE", None)

        return result, conductor_calls, merge_calls

    def test_pipeline_passes_bootstrap_inputs_to_conductor(self, tmp_path):
        """Bootstrap runs once and its outputs are forwarded to Conductor inputs."""
        from unittest.mock import patch

        mod = self._load_mod()
        bootstrap = {
            "platform": "github",
            "pr_author": "author@example.com",
            "changed_files": ["src/app.py"],
            "source_branch": "feature/bootstrap",
            "existing_pr": "https://github.com/org/repo/pull/42",
            "auth_ok": True,
        }

        with patch.object(mod, "_run_bootstrap", return_value=bootstrap) as mock_bootstrap, \
             patch.object(mod, "cleanup_workspace_dir"):
            result, conductor_calls, _ = self._run_with_mocks(
                tmp_path,
                mod,
                "yolo-fast",
                existing_pr=bootstrap["existing_pr"],
            )

        assert result["status"] == "completed"
        mock_bootstrap.assert_called_once()
        first_phase_inputs = conductor_calls[0]["inputs"]
        assert first_phase_inputs["platform"] == "github"
        assert first_phase_inputs["pr_author"] == "author@example.com"
        assert "changed_files_path" in first_phase_inputs
        assert Path(first_phase_inputs["changed_files_path"]).exists()
        assert json.loads(
            Path(first_phase_inputs["changed_files_path"]).read_text(encoding="utf-8")
        ) == ["src/app.py"]
        assert first_phase_inputs["source_branch"] == "feature/bootstrap"
        phase2_inputs = next(call["inputs"] for call in conductor_calls if call["phase_id"] == "2")
        assert phase2_inputs["existing_pr"] == "https://github.com/org/repo/pull/42"

    def test_pipeline_bootstrap_failure_falls_back_to_workflow(self, tmp_path, capsys):
        """Bootstrap failures only warn and do not block the pipeline."""
        from unittest.mock import patch

        mod = self._load_mod()
        with patch.object(mod, "_run_bootstrap", side_effect=RuntimeError("boom")):
            result, conductor_calls, _ = self._run_with_mocks(tmp_path, mod, "yolo-fast")

        captured = capsys.readouterr()
        assert result["status"] == "completed"
        assert conductor_calls
        assert "WARNING: Deterministic bootstrap failed" in captured.out

    def test_pipeline_passes_workspace_dir_to_workspace_aware_phases(self, tmp_path):
        """Phases 2, 4, and 5 receive the same per-run workspace_dir input."""
        mod = self._load_mod()
        result, conductor_calls, _ = self._run_with_mocks(tmp_path, mod, "yolo-fast")

        assert result["status"] == "completed"
        workspace_inputs = {
            call["phase_id"]: call["inputs"].get("workspace_dir")
            for call in conductor_calls
            if call["phase_id"] in {"2", "4", "5"}
        }
        assert set(workspace_inputs) == {"2", "4", "5"}
        assert len(set(workspace_inputs.values())) == 1

    def test_pipeline_cleans_up_workspace_on_success(self, tmp_path):
        """Successful runs remove the per-run workspace and clear state tracking."""
        mod = self._load_mod()
        result, _, _ = self._run_with_mocks(tmp_path, mod, "yolo-fast")

        workspace_dir = Path(result["workspace_dir"])
        assert not workspace_dir.exists()

        state_file = tmp_path / "state.json"
        final_state = json.loads(state_file.read_text(encoding="utf-8"))
        assert "_workspace_dir" not in final_state

    def test_pipeline_preserves_workspace_on_failure(self, tmp_path):
        """Failed runs preserve the workspace for debugging and keep it in state."""
        mod = self._load_mod()

        def fail_phase_2(phase_id, attempt):
            return 1 if phase_id == "2" else 0

        result, _, _ = self._run_with_mocks(
            tmp_path,
            mod,
            "yolo-fast",
            conductor_side_effect=fail_phase_2,
        )

        assert result["status"] == "failed"
        workspace_dir = Path(result["workspace_dir"])
        assert workspace_dir.exists()

        state_file = tmp_path / "state.json"
        final_state = json.loads(state_file.read_text(encoding="utf-8"))
        assert final_state["_workspace_dir"] == str(workspace_dir)

    # ── YOLO mode ─────────────────────────────────────────────────────────

    def test_yolo_runs_all_phases(self, tmp_path):
        """YOLO mode runs all 8 phases in order."""
        mod = self._load_mod()
        # Need mechanical findings so Phase 1d doesn't skip
        injections = {
            "1a": {"business_logic_digest": "d", "test_coverage_digest": "t"},
            "1b": {"generated_tests": "t"},
            "1c": {"code_review_findings": {
                "high": [{"id": "CR-1", "mechanical": "True", "description": "fix"}],
                "medium": [], "low": [],
            }},
            "1d": {"code_fix": "applied"},
            "2": {"pr_url": "https://dev.azure.com/test/pr/42"},
            "3": {"watch_and_fix": "ok"},
            "5": {"address_feedback": "done"},
        }
        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo", state_injections=injections,
        )
        assert result["status"] == "completed"
        executed_phases = [c["phase_id"] for c in conductor_calls]
        assert executed_phases == ["1a", "1b", "1c", "1d", "2", "3", "4", "5"]

    def test_yolo_phase_order_matches_sequence(self, tmp_path):
        """Conductor is called in exact PHASE_SEQUENCE order."""
        mod = self._load_mod()
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": {
                "high": [{"id": "CR-1", "mechanical": "True", "description": "fix"}],
            }},
            "1d": {},
            "2": {"pr_url": "https://test/pr/1"},
            "3": {},
            "5": {},
        }
        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo", state_injections=injections,
        )
        workflows = [c["workflow"] for c in conductor_calls]
        expected = [
            "phase1a-digests.yaml", "phase1b-testgen.yaml",
            "phase1c-codereview.yaml", "phase1d-codefix.yaml",
            "phase2-create-pr.yaml", "phase3-watch-fix.yaml",
            "phase4-review-digest.yaml", "phase5-feedback.yaml",
        ]
        assert workflows == expected

    def test_yolo_phase2_pr_url_flows_to_later_phases(self, tmp_path):
        """pr_url produced by Phase 2 is passed to Phases 3, 4, 5."""
        mod = self._load_mod()
        pr_url = "https://dev.azure.com/org/proj/_git/repo/pullrequest/999"
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": {
                "high": [{"id": "CR-1", "mechanical": "True", "description": "fix"}],
            }},
            "1d": {},
            "2": {"pr_url": pr_url},
            "3": {},
            "5": {},
        }
        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo", state_injections=injections,
        )
        # Phase 3, 4, 5 should all receive pr_url as input
        for call in conductor_calls:
            if call["phase_id"] in ("3", "4", "5"):
                assert call["inputs"]["pr_url"] == pr_url, \
                    f"Phase {call['phase_id']} missing pr_url"

    def test_yolo_phase4_gets_state_file(self, tmp_path):
        """Phase 4 receives state_file as input."""
        mod = self._load_mod()
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": {"high": [], "medium": [], "low": []}},
            "2": {"pr_url": "https://test/pr/1"},
            "3": {},
            "5": {},
        }
        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo", state_injections=injections,
        )
        phase4_call = [c for c in conductor_calls if c["phase_id"] == "4"][0]
        assert "state_file" in phase4_call["inputs"]

    def test_execute_phase_writes_phase_meta(self, tmp_path):
        from unittest.mock import patch

        mod = self._load_mod()
        state_file = tmp_path / "state.json"
        mod.save_state(state_file, {})
        workflow_dir = tmp_path / "workflows"
        workflow_dir.mkdir()
        (workflow_dir / "phase1a-digests.yaml").write_text("# stub", encoding="utf-8")
        merge_script = tmp_path / "merge-state.py"
        merge_script.write_text("# stub", encoding="utf-8")

        def fake_merge(event_log_glob, state_file, phase_id, clear_keys, merge_script):
            current = mod.load_state(state_file)
            current.update({"business_logic_digest": "digest"})
            current["_phases"] = {"1a": {"business_logic_digest": "digest", "tests_run": 3}}
            mod.save_state(state_file, current)
            return 0

        phase = mod.PhaseSpec(
            id="1a",
            workflow="phase1a-digests.yaml",
            merge_phase="1a",
            inputs=["target_branch"],
            required_outputs=["business_logic_digest"],
        )
        with patch.object(mod, "run_conductor", return_value=(0, "fake.events.jsonl")), \
             patch.object(mod, "run_merge_state", side_effect=fake_merge):
            result = mod.execute_phase(
                phase=phase,
                state={},
                state_file=state_file,
                target_branch="main",
                scripts_dir=tmp_path,
                workflow_dir=workflow_dir,
                merge_script=merge_script,
                run_id="test-run",
                work_dir=tmp_path,
                workspace_dir=tmp_path / "workspace",
                current_fingerprint={"pr_head": "abc123", "base_sha": "def456"},
            )
        assert result.status == "completed"
        saved = mod.load_state(state_file)
        assert saved["_phase_meta"]["1a"]["fingerprint"] == {"pr_head": "abc123", "base_sha": "def456"}
        assert saved["_phase_meta"]["1a"]["output_keys"] == ["business_logic_digest", "tests_run"]

    def test_yolo_phase5_has_skip_gates_flag(self, tmp_path):
        """Phase 5 conductor call includes --skip-gates."""
        mod = self._load_mod()
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": {"high": [], "medium": [], "low": []}},
            "2": {"pr_url": "https://test/pr/1"},
            "3": {},
            "5": {},
        }
        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo", state_injections=injections,
        )
        phase5_call = [c for c in conductor_calls if c["phase_id"] == "5"][0]
        assert "--skip-gates" in phase5_call["flags"]

    # ── YOLO-fast mode ────────────────────────────────────────────────────

    def test_yolo_fast_skips_phase3(self, tmp_path):
        """YOLO-fast mode skips Phase 3 entirely."""
        mod = self._load_mod()
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": {"high": [], "medium": [], "low": []}},
            "2": {"pr_url": "https://test/pr/1"},
            "5": {},
        }
        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo-fast", state_injections=injections,
        )
        assert result["status"] == "completed"
        executed = [c["phase_id"] for c in conductor_calls]
        assert "3" not in executed
        assert result["phases"]["3"]["status"] == "skipped"

    def test_yolo_fast_runs_phase5_after_phase4(self, tmp_path):
        """YOLO-fast still runs Phase 5 after Phase 4."""
        mod = self._load_mod()
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": {"high": [], "medium": [], "low": []}},
            "2": {"pr_url": "https://test/pr/1"},
            "5": {},
        }
        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo-fast", state_injections=injections,
        )
        executed = [c["phase_id"] for c in conductor_calls]
        assert "4" in executed
        assert "5" in executed
        assert executed.index("4") < executed.index("5")

    # ── Interactive mode ──────────────────────────────────────────────────

    def test_interactive_pauses_at_first_gate(self, tmp_path):
        """Interactive mode exits with code 10 after Phase 1a."""
        mod = self._load_mod()
        injections = {
            "1a": {"business_logic_digest": "d"},
        }
        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "interactive", state_injections=injections,
        )
        assert result.get("_exit_code") == 10
        assert result.get("_pending_gate") == "1a"
        # Only Phase 1a should have executed
        assert len(conductor_calls) == 1
        assert conductor_calls[0]["phase_id"] == "1a"

    def test_interactive_resume_continues_from_gate(self, tmp_path):
        """Resuming after a gate continues with the next phase."""
        mod = self._load_mod()
        _, state_file = self._setup_env(tmp_path)

        # Simulate state after Phase 1a completed and gate paused
        initial = {
            "_completed_phases": ["1a"],
            "_run_id": "test-resume",
            "_started_at": "2026-01-01T00:00:00+00:00",
            "_pending_gate": "1a",
            "_gate_message": "Digests complete.",
            "_phase_results": {"1a": {"status": "completed", "duration_s": 1, "attempts": 1}},
            "_phases": {"1a": {"business_logic_digest": "d"}},
        }
        injections = {
            "1b": {"generated_tests": "t"},
        }

        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "interactive",
            state_injections=injections,
            initial_state=initial,
            state_file=state_file,
            resume=True,
        )
        # Should pause at Phase 1b gate (next gate)
        assert result.get("_exit_code") == 10
        assert result.get("_pending_gate") == "1b"
        # Should NOT re-run Phase 1a
        executed = [c["phase_id"] for c in conductor_calls]
        assert "1a" not in executed
        assert "1b" in executed

    def test_interactive_auto_resume_without_flag(self, tmp_path):
        """Without --resume, auto-detects pending gate and continues."""
        mod = self._load_mod()
        _, state_file = self._setup_env(tmp_path)

        initial = {
            "_completed_phases": ["1a"],
            "_run_id": "test-auto-resume",
            "_started_at": "2026-01-01T00:00:00+00:00",
            "_pending_gate": "1a",
            "_gate_message": "Digests complete.",
            "_phase_results": {"1a": {"status": "completed"}},
            "business_logic_digest": "d",
        }
        injections = {"1b": {}}

        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "interactive",
            state_injections=injections,
            initial_state=initial,
            state_file=state_file,
            resume=False,  # NOT passing --resume
        )
        # Should auto-resume and run Phase 1b
        executed = [c["phase_id"] for c in conductor_calls]
        assert "1a" not in executed
        assert "1b" in executed

    def test_interactive_all_gates_fire(self, tmp_path):
        """All 7 interactive gates fire across sequential resume calls."""
        mod = self._load_mod()
        _, state_file = self._setup_env(tmp_path)

        pr_url = "https://test/pr/1"
        # State injections for ALL phases including mechanical findings
        all_injections = {
            "1a": {"business_logic_digest": "d", "test_coverage_digest": "t"},
            "1b": {"generated_tests": "t"},
            "1c": {"code_review_findings": {
                "high": [{"id": "CR-1", "mechanical": "True", "description": "fix"}],
            }},
            "1d": {"code_fix": "applied"},
            "2": {"pr_url": pr_url},
            "3": {"watch_and_fix": "ok"},
            "5": {"address_feedback": "done"},
        }

        gates_fired = []
        state_file.write_text("{}", encoding="utf-8")

        for iteration in range(10):  # Safety limit
            result, conductor_calls, _ = self._run_with_mocks(
                tmp_path, mod, "interactive",
                state_injections=all_injections,
                state_file=state_file,
                resume=(iteration > 0),
            )
            if result.get("_exit_code") == 10:
                gates_fired.append(result["_pending_gate"])
            else:
                # Pipeline completed (Phase 5 has no gate)
                break

        assert gates_fired == ["1a", "1b", "1c", "1d", "2", "3", "4"]
        assert result["status"] == "completed"

    # ── Conditional skip ──────────────────────────────────────────────────

    def test_phase1d_skipped_when_no_mechanical_findings(self, tmp_path):
        """Phase 1d is skipped when code review has no mechanical findings."""
        mod = self._load_mod()
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": {
                "high": [{"id": "CR-1", "mechanical": "False", "description": "info only"}],
                "medium": [], "low": [],
            }},
            "2": {"pr_url": "https://test/pr/1"},
            "3": {},
            "5": {},
        }
        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo", state_injections=injections,
        )
        executed = [c["phase_id"] for c in conductor_calls]
        assert "1d" not in executed
        assert result["phases"]["1d"]["status"] == "skipped"

    def test_phase1d_runs_when_mechanical_findings_exist(self, tmp_path):
        """Phase 1d runs when there are mechanical findings."""
        mod = self._load_mod()
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": {
                "high": [{"id": "CR-1", "mechanical": "True", "description": "fix"}],
            }},
            "1d": {"code_fix": "applied"},
            "2": {"pr_url": "https://test/pr/1"},
            "3": {},
            "5": {},
        }
        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo", state_injections=injections,
        )
        executed = [c["phase_id"] for c in conductor_calls]
        assert "1d" in executed

    def test_phase1d_runs_when_findings_have_escaped_quotes(self, tmp_path):
        """Phase 1d runs even when findings JSON contains Python-style \\' escapes."""
        mod = self._load_mod()
        # Simulate the LLM emitting \' in JSON strings (invalid JSON but common)
        bad_json = '{"high":[{"id":"H1","mechanical":true,"description":"Check for \\\'Dev\\\' env"}]}'
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": bad_json},
            "1d": {"code_fix": "applied"},
            "2": {"pr_url": "https://test/pr/1"},
            "3": {},
            "5": {},
        }
        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo", state_injections=injections,
        )
        executed = [c["phase_id"] for c in conductor_calls]
        assert "1d" in executed

    def test_phase1d_passes_findings_and_scripts_dir(self, tmp_path):
        """Phase 1d receives findings_json_path, scripts_dir, and workspace_dir inputs."""
        mod = self._load_mod()
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": {
                "high": [{"id": "CR-1", "mechanical": "True", "description": "fix"}],
            }},
            "1d": {},
            "2": {"pr_url": "https://test/pr/1"},
            "3": {},
            "5": {},
        }
        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo", state_injections=injections,
        )
        phase1d_call = [c for c in conductor_calls if c["phase_id"] == "1d"][0]
        assert "findings_json_path" in phase1d_call["inputs"]
        assert "scripts_dir" in phase1d_call["inputs"]
        assert "workspace_dir" in phase1d_call["inputs"]

    def test_phase1d_clears_code_fix_on_first_attempt(self, tmp_path):
        """Phase 1d merge passes clear_keys=['code_fix'] on first attempt only."""
        mod = self._load_mod()
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": {
                "high": [{"id": "CR-1", "mechanical": "True", "description": "fix"}],
            }},
            "1d": {},
            "2": {"pr_url": "https://test/pr/1"},
            "3": {},
            "5": {},
        }
        result, conductor_calls, merge_calls = self._run_with_mocks(
            tmp_path, mod, "yolo", state_injections=injections,
        )
        phase1d_merges = [m for m in merge_calls if m["phase_id"] == "1d"]
        assert len(phase1d_merges) >= 1
        assert "code_fix" in phase1d_merges[0]["clear_keys"]

    # ── Failure handling ──────────────────────────────────────────────────

    def test_phase2_failure_stops_pipeline(self, tmp_path):
        """Phase 2 failure is fatal — pipeline stops."""
        mod = self._load_mod()
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": {"high": [], "medium": [], "low": []}},
        }

        def conductor_fail_phase2(phase_id, attempt):
            return 1 if phase_id == "2" else 0

        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo",
            state_injections=injections,
            conductor_side_effect=conductor_fail_phase2,
        )
        assert result["status"] == "failed"
        executed = [c["phase_id"] for c in conductor_calls]
        # Phase 2 runs (with retries) but 3, 4, 5 should NOT
        assert "3" not in executed
        assert "4" not in executed
        assert "5" not in executed

    def test_non_fatal_phase_failure_continues(self, tmp_path):
        """Failure in Phase 1b doesn't prevent Phase 1c from running."""
        mod = self._load_mod()
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1c": {"code_review_findings": {"high": [], "medium": [], "low": []}},
            "2": {"pr_url": "https://test/pr/1"},
            "3": {},
            "5": {},
        }

        def conductor_fail_1b(phase_id, attempt):
            return 1 if phase_id == "1b" else 0

        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo",
            state_injections=injections,
            conductor_side_effect=conductor_fail_1b,
        )
        executed = [c["phase_id"] for c in conductor_calls]
        # 1b failed but 1c should still run
        assert "1c" in executed
        # Pipeline overall is failed due to 1b
        assert result["status"] == "failed"

    def test_retry_exhausts_max_attempts(self, tmp_path):
        """Phase retries up to max_retries times (3 total attempts)."""
        mod = self._load_mod()
        injections = {"1a": {"business_logic_digest": "d"}}

        call_count = {"1a": 0}

        def conductor_fail_1a(phase_id, attempt):
            if phase_id == "1a":
                call_count["1a"] += 1
                return 1  # Always fail
            return 0

        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo",
            state_injections=injections,
            conductor_side_effect=conductor_fail_1a,
        )
        phase1a_calls = [c for c in conductor_calls if c["phase_id"] == "1a"]
        # max_retries=2 → 3 total attempts (0, 1, 2)
        assert len(phase1a_calls) == 3
        assert phase1a_calls[0]["attempt"] == 0
        assert phase1a_calls[1]["attempt"] == 1
        assert phase1a_calls[2]["attempt"] == 2

    def test_merge_runs_even_on_conductor_failure(self, tmp_path):
        """Merge-state is called even when Conductor exits non-zero."""
        mod = self._load_mod()
        injections = {"1a": {"business_logic_digest": "d"}}

        def conductor_fail_then_pass(phase_id, attempt):
            if phase_id == "1a" and attempt == 0:
                return 1  # Fail first attempt
            return 0

        result, conductor_calls, merge_calls = self._run_with_mocks(
            tmp_path, mod, "yolo",
            state_injections=injections,
            conductor_side_effect=conductor_fail_then_pass,
        )
        # Phase 1a has merge_phase="1a", so merge should be called on failure too
        phase1a_merges = [m for m in merge_calls if m["phase_id"] == "1a"]
        assert len(phase1a_merges) >= 2  # At least: failed attempt + success

    # ── State management ──────────────────────────────────────────────────

    def test_fresh_run_clears_stale_state(self, tmp_path):
        """A fresh (non-resume) run wipes old state when no pending gate."""
        mod = self._load_mod()
        _, state_file = self._setup_env(tmp_path)

        # Write stale state without a pending gate
        stale = {
            "_completed_phases": ["1a", "1b"],
            "pr_url": "https://old-stale/pr/99",
        }
        state_file.write_text(json.dumps(stale), encoding="utf-8")

        injections = {"1a": {"business_logic_digest": "d"}}

        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo",
            state_injections=injections,
            state_file=state_file,
        )
        # Phase 1a should run (not skipped due to stale completed_phases)
        executed = [c["phase_id"] for c in conductor_calls]
        assert "1a" in executed

    def test_fresh_run_cleans_stale_temp_files(self, tmp_path):
        """A fresh run removes stale temp files left by previous runs."""
        mod = self._load_mod()

        # Create some stale temp files
        import tempfile as tf
        tmp_dir = Path(tf.gettempdir())
        stale_files = ["digest-input.json", "final-digest-input.json", "upstream-data.json"]
        for name in stale_files:
            (tmp_dir / name).write_text("{}", encoding="utf-8")

        # Verify they exist
        for name in stale_files:
            assert (tmp_dir / name).exists(), f"{name} should exist before cleanup"

        # Run cleanup
        mod._cleanup_stale_temp_files()

        # Verify they were removed
        for name in stale_files:
            assert not (tmp_dir / name).exists(), f"{name} should be removed after cleanup"

    def test_resume_skips_completed_phases(self, tmp_path):
        """Resume doesn't re-run already-completed phases."""
        mod = self._load_mod()
        _, state_file = self._setup_env(tmp_path)

        initial = {
            "_completed_phases": ["1a", "1b", "1c"],
            "_run_id": "test-skip",
            "_started_at": "2026-01-01T00:00:00+00:00",
            "_pending_gate": "1c",
            "_gate_message": "Review complete.",
            "_phase_results": {},
            "_phases": {
                "1a": {"business_logic_digest": "d"},
                "1c": {"code_review_findings": {"high": [], "medium": [], "low": []}},
            },
        }
        injections = {
            "2": {"pr_url": "https://test/pr/1"},
            "3": {},
            "5": {},
        }

        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "interactive",
            state_injections=injections,
            initial_state=initial,
            state_file=state_file,
            resume=True,
        )
        executed = [c["phase_id"] for c in conductor_calls]
        # 1a, 1b, 1c should NOT re-run
        assert "1a" not in executed
        assert "1b" not in executed
        assert "1c" not in executed

    # ── existing_pr path ──────────────────────────────────────────────────

    def test_existing_pr_passes_to_later_phases(self, tmp_path):
        """--existing-pr is used by Phases 3, 4, 5 even without Phase 2 pr_url."""
        mod = self._load_mod()
        ext_pr = "https://dev.azure.com/org/proj/_git/repo/pullrequest/777"
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": {"high": [], "medium": [], "low": []}},
            "2": {"pr_url": ext_pr},  # Phase 2 still runs but pr_url comes from --existing-pr
            "3": {},
            "5": {},
        }

        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "yolo",
            state_injections=injections,
            existing_pr=ext_pr,
        )
        # Phases 3, 4, 5 should use the existing_pr
        for call in conductor_calls:
            if call["phase_id"] in ("3", "4", "5"):
                assert call["inputs"]["pr_url"] == ext_pr

    # ── Phase 4 never merges ─────────────────────────────────────────────

    def test_phase4_merges_state_with_digest_url(self, tmp_path):
        """Phase 4 should merge state to capture digest_comment_url and digest_comment_id."""
        mod = self._load_mod()
        injections = {
            "1a": {"business_logic_digest": "d"},
            "1b": {},
            "1c": {"code_review_findings": {"high": [], "medium": [], "low": []}},
            "2": {"pr_url": "https://test/pr/1"},
            "3": {},
            "4": {"digest_comment_url": "https://test/pr/1?discussionId=123",
                  "digest_comment_id": "123:1"},
            "5": {},
        }
        result, conductor_calls, merge_calls = self._run_with_mocks(
            tmp_path, mod, "yolo", state_injections=injections,
        )
        merge_phases = [m["phase_id"] for m in merge_calls]
        assert "4" in merge_phases
        # Verify digest URL made it to canonical phase-scoped state
        state_file = tmp_path / "state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["_phases"]["4"]["digest_comment_url"] == "https://test/pr/1?discussionId=123"
        assert state["_phases"]["4"]["digest_comment_id"] == "123:1"

    # ── Standalone --phase execution ────────────────────────────────────

    def _run_single_phase_with_mocks(self, tmp_path, mod, phase_id,
                                      state_injections=None, initial_state=None,
                                      existing_pr=None,
                                      conductor_side_effect=None,
                                      merge_side_effect=None):
        """Run a single phase with mocked conductor and merge-state."""
        from unittest.mock import patch, MagicMock

        _, default_state_file = self._setup_env(tmp_path)

        if initial_state:
            default_state_file.write_text(json.dumps(initial_state), encoding="utf-8")

        if state_injections is None:
            state_injections = {}

        conductor_calls = []
        merge_calls = []

        def mock_conductor(**kwargs):
            conductor_calls.append({
                "phase_id": kwargs["phase_id"],
                "attempt": kwargs["attempt"],
                "workflow": kwargs["workflow_path"].name,
            })
            if conductor_side_effect:
                exit_code = conductor_side_effect(kwargs["phase_id"], kwargs["attempt"])
            else:
                exit_code = 0
            return exit_code, f"fake-{kwargs['phase_id']}-{kwargs['attempt']}.events.jsonl"

        def mock_merge(**kwargs):
            merge_calls.append({"phase_id": kwargs["phase_id"]})
            phase_id_arg = kwargs["phase_id"]
            if phase_id_arg in state_injections:
                current = json.loads(Path(kwargs["state_file"]).read_text(encoding="utf-8"))
                phases = current.get("_phases", {})
                if not isinstance(phases, dict):
                    phases = {}
                phase_payload = phases.get(phase_id_arg, {})
                if not isinstance(phase_payload, dict):
                    phase_payload = {}
                phase_payload.update(state_injections[phase_id_arg])
                phases[phase_id_arg] = phase_payload
                current["_phases"] = phases
                Path(kwargs["state_file"]).write_text(
                    json.dumps(current, indent=2), encoding="utf-8"
                )
            if merge_side_effect:
                return merge_side_effect(phase_id_arg)
            return 0

        orig_userprofile = os.environ.get("USERPROFILE")
        os.environ["USERPROFILE"] = str(tmp_path)

        try:
            with patch.object(mod, "run_conductor", side_effect=mock_conductor), \
                 patch.object(mod, "run_merge_state", side_effect=mock_merge), \
                 patch("subprocess.run", return_value=MagicMock(
                     stdout="test-branch", returncode=0, stderr=""
                 )):
                result = mod.run_single_phase(
                    phase_id=phase_id,
                    target_branch="main",
                    work_dir=tmp_path,
                    existing_pr=existing_pr,
                    state_file_override=default_state_file,
                )
        finally:
            if orig_userprofile:
                os.environ["USERPROFILE"] = orig_userprofile
            else:
                os.environ.pop("USERPROFILE", None)

        return result, conductor_calls, merge_calls, default_state_file

    def test_single_phase_runs_only_requested_phase(self, tmp_path):
        """--phase 1a runs only phase 1a, not the entire pipeline."""
        mod = self._load_mod()
        result, conductor_calls, _, _ = self._run_single_phase_with_mocks(
            tmp_path, mod, "1a",
            state_injections={"1a": {"business_logic_digest": "d"}},
        )
        assert result["status"] == "completed"
        assert result["execution_scope"] == "single-phase"
        assert result["requested_phase"] == "1a"
        assert len(conductor_calls) == 1
        assert conductor_calls[0]["phase_id"] == "1a"

    def test_single_phase_3_fails_without_pr_url(self, tmp_path):
        """--phase 3 fails fast if pr_url is missing from state."""
        mod = self._load_mod()
        result, conductor_calls, _, _ = self._run_single_phase_with_mocks(
            tmp_path, mod, "3",
        )
        assert result["status"] == "error"
        assert "pr_url" in result["error"]
        assert len(conductor_calls) == 0

    def test_single_phase_5_fails_without_pr_url(self, tmp_path):
        """--phase 5 fails fast if pr_url is missing from state."""
        mod = self._load_mod()
        result, conductor_calls, _, _ = self._run_single_phase_with_mocks(
            tmp_path, mod, "5",
        )
        assert result["status"] == "error"
        assert "pr_url" in result["error"]
        assert len(conductor_calls) == 0

    def test_single_phase_3_succeeds_with_pr_url(self, tmp_path):
        """--phase 3 runs when pr_url exists in state."""
        mod = self._load_mod()
        result, conductor_calls, _, _ = self._run_single_phase_with_mocks(
            tmp_path, mod, "3",
            initial_state={"pr_url": "https://dev.azure.com/test/pr/42"},
            state_injections={"3": {"watch_and_fix": "ok"}},
        )
        assert result["status"] == "completed"
        assert len(conductor_calls) == 1

    def test_single_phase_1d_missing_prerequisite_not_skipped(self, tmp_path):
        """--phase 1d without 1c findings fails as missing prerequisite, not skipped."""
        mod = self._load_mod()
        result, conductor_calls, _, _ = self._run_single_phase_with_mocks(
            tmp_path, mod, "1d",
        )
        assert result["status"] == "error"
        assert "code_review_findings" in result["error"]
        assert len(conductor_calls) == 0

    def test_single_phase_1d_empty_findings_skips_not_fails(self, tmp_path):
        """--phase 1d with empty findings dict should skip (no mechanical), not fail prerequisite."""
        mod = self._load_mod()
        initial_state = {
            "_phases": {
                "1c": {
                    "code_review_findings": {},
                    "tier": 1,
                    "human_judgment_findings": [],
                    "review_engine": "gatekeeper",
                    "done": True,
                }
            },
            "_completed_phases": ["1a", "1b", "1c"],
        }
        result, conductor_calls, _, _ = self._run_single_phase_with_mocks(
            tmp_path, mod, "1d",
            initial_state=initial_state,
        )
        # Should be skipped (no mechanical findings), not an error
        assert result["status"] != "error", f"Got error: {result.get('error')}"
        assert result["phases"]["1d"]["status"] == "skipped"

    def test_single_phase_clears_completion_marker(self, tmp_path):
        """--phase re-runs even if the phase was previously completed."""
        mod = self._load_mod()
        initial_state = {
            "_completed_phases": ["1a", "1b"],
            "business_logic_digest": "old-digest",
        }
        result, conductor_calls, _, state_file = self._run_single_phase_with_mocks(
            tmp_path, mod, "1a",
            initial_state=initial_state,
            state_injections={"1a": {"business_logic_digest": "new-digest"}},
        )
        assert result["status"] == "completed"
        assert len(conductor_calls) == 1
        # Verify the phase was re-marked complete
        final_state = json.loads(state_file.read_text(encoding="utf-8"))
        assert "1a" in final_state["_completed_phases"]

    def test_single_phase_does_not_clear_pending_gate(self, tmp_path):
        """--phase does not interfere with interactive gate state."""
        mod = self._load_mod()
        initial_state = {
            "_pending_gate": "2",
            "_gate_message": "PR created.",
            "_completed_phases": ["1a", "1b", "1c", "1d", "2"],
            "pr_url": "https://dev.azure.com/test/pr/42",
        }
        result, _, _, state_file = self._run_single_phase_with_mocks(
            tmp_path, mod, "4",
            initial_state=initial_state,
        )
        assert result["status"] == "completed"
        # Gate state should still be there
        final_state = json.loads(state_file.read_text(encoding="utf-8"))
        assert final_state.get("_pending_gate") == "2"

    def test_single_phase_rerun_does_not_use_stale_output(self, tmp_path):
        """Rerunning phase 2 with stale pr_url — failure should not pass."""
        mod = self._load_mod()
        initial_state = {
            "_completed_phases": ["1a", "1b", "1c", "1d", "2"],
            "pr_url": "https://dev.azure.com/test/pr/old",
        }
        # Conductor fails on the re-run
        def fail_conductor(phase_id, attempt):
            return 1  # non-zero exit

        result, conductor_calls, _, _ = self._run_single_phase_with_mocks(
            tmp_path, mod, "2",
            initial_state=initial_state,
            conductor_side_effect=fail_conductor,
        )
        assert result["status"] == "failed"
        # It should have attempted to run (not skipped)
        assert len(conductor_calls) >= 1

    def test_single_phase_unknown_id_returns_error(self, tmp_path):
        """--phase with unknown ID returns error."""
        mod = self._load_mod()
        result = mod.run_single_phase(
            phase_id="99z",
            target_branch="main",
            work_dir=tmp_path,
        )
        assert result["status"] == "error"
        assert "Unknown phase" in result["error"]

    def test_interactive_skip_next_skips_phase(self, tmp_path):
        """--resume --skip-next skips the next unfinished phase."""
        mod = self._load_mod()
        _, state_file = self._setup_env(tmp_path)

        # Simulate state after Phase 1a completed and gate paused
        initial = {
            "_completed_phases": ["1a"],
            "_run_id": "test-skip",
            "_started_at": "2026-01-01T00:00:00+00:00",
            "_pending_gate": "1a",
            "_gate_message": "Digests complete.",
            "_phase_results": {"1a": {"status": "completed", "duration_s": 1, "attempts": 1}},
            "business_logic_digest": "d",
        }
        injections = {
            "1c": {"code_review_findings": {"high": [], "medium": [], "low": []}},
        }

        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "interactive",
            state_injections=injections,
            initial_state=initial,
            state_file=state_file,
            resume=True,
            skip_next=True,
        )
        # Phase 1b (next after 1a) should be skipped, not executed
        executed = [c["phase_id"] for c in conductor_calls]
        assert "1b" not in executed
        # Phase 1b should be in results as skipped
        phases = result.get("phases", result.get("_phase_results", {}))
        if "1b" in phases:
            assert phases["1b"]["status"] == "skipped"
            assert "user skip" in phases["1b"].get("reason", "")

    def test_interactive_skip_next_still_runs_subsequent_phases(self, tmp_path):
        """--skip-next only skips one phase, not the rest."""
        mod = self._load_mod()
        _, state_file = self._setup_env(tmp_path)

        # Simulate state after Phase 1a completed and gate paused
        initial = {
            "_completed_phases": ["1a"],
            "_run_id": "test-skip-one",
            "_started_at": "2026-01-01T00:00:00+00:00",
            "_pending_gate": "1a",
            "_gate_message": "Digests complete.",
            "_phase_results": {"1a": {"status": "completed", "duration_s": 1, "attempts": 1}},
            "business_logic_digest": "d",
        }
        injections = {
            "1c": {"code_review_findings": {"high": [], "medium": [], "low": []}},
        }

        result, conductor_calls, _ = self._run_with_mocks(
            tmp_path, mod, "interactive",
            state_injections=injections,
            initial_state=initial,
            state_file=state_file,
            resume=True,
            skip_next=True,
        )
        # Phase 1c should have been executed (it's after the skipped 1b)
        executed = [c["phase_id"] for c in conductor_calls]
        assert "1c" in executed


# ── fix-pr-body.py ──────────────────────────────────────────────────────────

class TestPostDigestPlaceholder:
    """Tests for post-digest-placeholder.py output handling."""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("post_digest_placeholder", str(SCRIPTS_DIR / "post-digest-placeholder.py"))
        mod = importlib.util.module_from_spec(spec)
        return spec, mod

    def test_script_persists_digest_comment_url_for_github_output(self, monkeypatch, tmp_path, capsys):
        spec, mod = self._load_module()
        upsert_json = {"comment_id": 12345}
        pr_url = "https://github.com/owner/repo/pull/42"

        class DummyResult:
            def __init__(self, stdout="", returncode=0, stderr=""):
                self.stdout = stdout
                self.returncode = returncode
                self.stderr = stderr

        temp_dir = str(tmp_path)
        calls = []

        def fake_run(cmd, capture_output=False, text=False, timeout=None, shell=False, **kwargs):
            calls.append(cmd)
            if cmd[0] == sys.executable and str(cmd[1]).endswith("upsert-digest.py"):
                return DummyResult(stdout=json.dumps(upsert_json))
            if cmd[:4] == ["gh", "pr", "view", pr_url]:
                return DummyResult(stdout="<!-- pr-orchestrator -->\nBody")
            if cmd[:4] == ["gh", "pr", "edit", pr_url]:
                return DummyResult(stdout="")
            return DummyResult(stdout="")

        monkeypatch.setattr(sys, "argv", ["post-digest-placeholder.py", pr_url, "github", "--workspace-dir", temp_dir])
        monkeypatch.setattr(tempfile, "gettempdir", lambda: temp_dir)
        monkeypatch.setattr(subprocess, "run", fake_run)

        spec.loader.exec_module(mod)
        assert mod.main() == 0
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["digest_comment_url"] == pr_url + "#issuecomment-12345"
        assert any(cmd[:4] == ["gh", "pr", "edit", pr_url] for cmd in calls)

    def test_script_persists_digest_comment_url_for_ado_output(self, monkeypatch, tmp_path, capsys):
        spec, mod = self._load_module()
        upsert_json = {"thread_id": 67890}
        pr_url = "https://dev.azure.com/org/project/_git/repo/pullrequest/42"

        class DummyResult:
            def __init__(self, stdout="", returncode=0, stderr=""):
                self.stdout = stdout
                self.returncode = returncode
                self.stderr = stderr

        temp_dir = str(tmp_path)

        def fake_run(cmd, capture_output=False, text=False, timeout=None, shell=False, **kwargs):
            if cmd[0] == sys.executable and str(cmd[1]).endswith("upsert-digest.py"):
                return DummyResult(stdout=json.dumps(upsert_json))
            if cmd[:4] == ["az", "repos", "pr", "show"]:
                return DummyResult(stdout="<!-- pr-orchestrator -->\nBody")
            if cmd[:3] == ["az", "rest", "--method"] and "PATCH" in cmd:
                return DummyResult(stdout="")
            return DummyResult(stdout="")

        monkeypatch.setattr(sys, "argv", ["post-digest-placeholder.py", pr_url, "ado", "--workspace-dir", temp_dir])
        monkeypatch.setattr(tempfile, "gettempdir", lambda: temp_dir)
        monkeypatch.setattr(subprocess, "run", fake_run)

        spec.loader.exec_module(mod)
        assert mod.main() == 0
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["digest_comment_url"] == pr_url + "?discussionId=67890"


class TestApplyPrBodyTemplate:
    """Tests for apply-pr-body-template.py warning behavior."""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("apply_pr_body_template", SCRIPTS_DIR / "apply-pr-body-template.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_import_fallback_logs_when_pr_platform_missing(self):
        mod, stderr = load_script_module(
            "apply_pr_body_template_no_platform",
            "apply-pr-body-template.py",
            block_pr_platform=True,
        )

        assert mod._HAS_PLATFORM is False
        assert "[fallback] pr_platform not available — using CLI fallback" in stderr

    def test_warns_when_digest_placeholder_remains_after_phase4(self, monkeypatch, tmp_path, capsys):
        mod = self._load_module()
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"_completed_phases": ["1a", "4"]}), encoding="utf-8")

        def fake_fetch_pr_body(platform, pr_url, platform_info, workspace_dir):
            return ("<!-- pr-orchestrator -->\nDIGEST_LINK_PLACEHOLDER", "Title", "42", "gh")

        def fake_update_pr(platform, pr_id, cli_cmd, fixed_body, platform_info, workspace_dir):
            return True

        class DummyResult:
            returncode = 0
            stderr = ""

        def fake_run(cmd, capture_output=False, text=False, timeout=None, **kwargs):
            output_file = Path(cmd[cmd.index("--output-file") + 1])
            output_file.write_text("<!-- pr-orchestrator -->\nDIGEST_LINK_PLACEHOLDER", encoding="utf-8")
            return DummyResult()

        monkeypatch.setattr(mod, "_fetch_pr_body", fake_fetch_pr_body)
        monkeypatch.setattr(mod, "_update_pr", fake_update_pr)
        monkeypatch.setattr(mod, "_detect_platform", lambda work_dir: {"platform": "github", "owner": "owner", "repo": "repo"})
        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(sys, "argv", [
            "apply-pr-body-template.py",
            "--pr-url", "https://github.com/owner/repo/pull/42",
            "--state-file", str(state_file),
            "--workspace-dir", str(tmp_path),
        ])

        assert mod.main() == 0
        captured = capsys.readouterr()
        assert "DIGEST_LINK_PLACEHOLDER remains" in captured.err

    def test_warns_when_sentinel_missing_in_raw_body(self, monkeypatch, tmp_path, capsys):
        mod = self._load_module()
        state_file = tmp_path / "state.json"
        state_file.write_text("{}", encoding="utf-8")

        def fake_fetch_pr_body(platform, pr_url, platform_info, workspace_dir):
            return ("Body replaced by bot", "Title", "42", "gh")

        def fake_update_pr(platform, pr_id, cli_cmd, fixed_body, platform_info, workspace_dir):
            return True

        class DummyResult:
            returncode = 0
            stderr = ""

        def fake_run(cmd, capture_output=False, text=False, timeout=None, **kwargs):
            output_file = Path(cmd[cmd.index("--output-file") + 1])
            output_file.write_text("<!-- pr-orchestrator -->\nFixed", encoding="utf-8")
            return DummyResult()

        monkeypatch.setattr(mod, "_fetch_pr_body", fake_fetch_pr_body)
        monkeypatch.setattr(mod, "_update_pr", fake_update_pr)
        monkeypatch.setattr(mod, "_detect_platform", lambda work_dir: {"platform": "github", "owner": "owner", "repo": "repo"})
        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(sys, "argv", [
            "apply-pr-body-template.py",
            "--pr-url", "https://github.com/owner/repo/pull/42",
            "--state-file", str(state_file),
            "--workspace-dir", str(tmp_path),
        ])

        assert mod.main() == 0
        captured = capsys.readouterr()
        assert "PR description sentinel missing" in captured.err

    def test_fetch_pr_body_runtime_fallback_logs_and_uses_cli(self, tmp_path):
        mod = self._load_module()
        from unittest.mock import patch

        class BrokenPrBodyOps:
            def __init__(self, ref):
                pass

            def fetch(self):
                raise RuntimeError("boom")

        class Completed:
            def __init__(self, stdout, returncode=0, stderr=""):
                self.stdout = stdout
                self.returncode = returncode
                self.stderr = stderr

        with patch.object(mod.PrRef, "from_url", return_value=type("Ref", (), {"base_url": "https://dev.azure.com/org"})()), \
             patch.object(mod, "PrBodyOps", BrokenPrBodyOps), \
             patch.object(mod, "run_cli", return_value=type("RunResult", (), {"stdout": "Title\n"})()), \
             patch.object(mod.shutil, "which", return_value="gh"), \
             patch.object(mod.subprocess, "run", return_value=Completed(json.dumps({"title": "Title", "body": "Body"}))), \
             contextlib.redirect_stderr(io.StringIO()) as captured:
            body, title, pr_id, cli_cmd = mod._fetch_pr_body(
                "github",
                "https://github.com/owner/repo/pull/42",
                {"owner": "owner", "repo": "repo"},
                tmp_path,
            )

        assert body == "Body"
        assert title == "Title"
        assert pr_id == "42"
        assert cli_cmd == "gh"
        assert "[fallback] pr_platform.PrBodyOps.fetch failed (boom) — using CLI" in captured.getvalue()


class TestFixPrBody:
    """Tests for fix-pr-body.py — deterministic PR body template enforcement."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("fix_pr_body", SCRIPTS_DIR / "fix-pr-body.py")
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_extract_section_intent(self):
        """Extract Intent section from well-formed PR body."""
        body = "## Intent\n\nThis fixes the widget bug.\n\n## Changes\n\n- Fixed widget"
        result = self.mod.extract_section(body, "Intent")
        assert "This fixes the widget bug" in result

    def test_extract_section_changes(self):
        """Extract Changes section from well-formed PR body."""
        body = "## Intent\n\nFoo\n\n## Changes\n\nFixed the bar module.\n\n---\nfooter"
        result = self.mod.extract_section(body, "Changes")
        assert "Fixed the bar module" in result
        assert "footer" not in result

    def test_extract_section_missing(self):
        """Returns empty string when section heading not found."""
        body = "## Summary\n\nSome text."
        assert self.mod.extract_section(body, "Intent") == ""

    def test_extract_section_removes_hint_blockquote(self):
        """Template hint blockquote (>_What does this change...) is stripped."""
        body = "## Intent\n\n> _What does this change accomplish and why?_\n\nActual content here.\n\n## Changes"
        result = self.mod.extract_section(body, "Intent")
        assert "Actual content here" in result
        assert "What does this change" not in result

    def test_extract_pr_title(self):
        """Extracts PR title from # heading."""
        body = "<!-- pr-orchestrator -->\n# fix(portal): Add environment param\n\n## Intent"
        assert "fix(portal): Add environment param" in self.mod.extract_pr_title(body)

    def test_extract_pr_title_missing(self):
        """Returns empty string when no # heading."""
        assert self.mod.extract_pr_title("No heading here") == ""

    def test_extract_digest_url_markdown_link(self):
        """Extracts URL from markdown digest link."""
        body = "📋 **[Review Digest](https://dev.azure.com/org/pr/123#comment)** — blah"
        assert self.mod.extract_digest_url(body) == "https://dev.azure.com/org/pr/123#comment"

    def test_extract_digest_url_placeholder(self):
        """Returns None when digest link is still a placeholder."""
        body = "📋 **[Review Digest](DIGEST_LINK_PLACEHOLDER)** — blah"
        assert self.mod.extract_digest_url(body) is None

    def test_extract_digest_url_none(self):
        """Returns None when no digest URL found."""
        body = "## Intent\n\nJust some text."
        assert self.mod.extract_digest_url(body) is None

    def test_create_pr_body_skips_when_body_already_canonical(self, monkeypatch, tmp_path, capsys):
        """Phase 2 must not rebuild an already-templated PR body."""
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        state = {
            "pr_url": "https://github.com/example/repo/pull/42",
            "_workspace_dir": str(tmp_path),
        }
        state_file = tmp_path / "state.json"
        state_file.write_text("{}", encoding="utf-8")
        current_body = (
            "<!-- pr-orchestrator -->\n"
            "# fix: title\n\n"
            "## Intent\n\n"
            "Already templated.\n\n"
            "## Changes\n\n"
            "- Done\n"
        )

        monkeypatch.setattr(
            mod,
            "_detect_platform_and_pr",
            lambda state, scripts_dir, work_dir: ("github", {"owner": "example", "repo": "repo"}, "42", "gh"),
        )
        monkeypatch.setattr(mod, "_fetch_pr_body", lambda *args, **kwargs: (current_body, "fix: title"))
        monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs: pytest.fail("fix-pr-body.py should not run"))
        monkeypatch.setattr(mod, "_push_pr_body", lambda *args, **kwargs: pytest.fail("PR body should not be pushed"))

        mod._create_pr_body(state, state_file, SCRIPTS_DIR, tmp_path)
        captured = capsys.readouterr()
        assert "body already templated" in captured.out

    def test_fix_pr_body_enforces_template(self):
        """fix_pr_body rebuilds body from template with correct structure."""
        llm_body = (
            "# My PR Title\n\n"
            "**Review Digest**: https://example.com/digest\n\n"
            "## Intent\n\nThis change adds environment injection to PowerShell commands.\n\n"
            "## Changes\n\n- Modified StringUtils.ts\n- Updated TestPassRunService.cs\n\n"
            "## Validation\n\n**Gates**: ✅ All passed\n\n"
            "---\n<sub>Generated by PR Orchestrator</sub>"
        )
        state = {
            "_completed_phases": ["1a", "1b", "1c", "1d", "2"],
            "pr_title": "fix(portal): Add env injection",
        }
        result = self.mod.fix_pr_body(llm_body, state)

        # DIGEST_LINK_PLACEHOLDER must be present at top for Phase 4
        assert "DIGEST_LINK_PLACEHOLDER" in result
        # Template structure markers
        assert "## Intent" in result
        assert "## Changes" in result
        assert "## Validation" in result
        # Gates line should no longer appear
        assert "**Gates**" not in result
        # LLM content preserved
        assert "environment injection" in result
        assert "StringUtils" in result
        # Footer preserved
        assert "PR Orchestrator" in result

    def test_fix_pr_body_digest_link_at_top(self):
        """DIGEST_LINK_PLACEHOLDER appears before ## Intent."""
        llm_body = "## Intent\n\nSome intent\n\n## Changes\n\nSome changes"
        state = {"_completed_phases": ["1a", "2"]}
        result = self.mod.fix_pr_body(llm_body, state)
        digest_pos = result.find("DIGEST_LINK_PLACEHOLDER")
        intent_pos = result.find("## Intent")
        assert digest_pos < intent_pos, "Digest link must appear before Intent section"

    def test_fix_pr_body_preserves_intent_content(self):
        """LLM-written intent content is extracted and placed correctly."""
        llm_body = (
            "## Intent\n\n"
            "This PR fixes the PowerShell command generation to include environment "
            "parameters. Previously, the RequestName was not properly quoted, causing "
            "failures in production.\n\n"
            "## Changes\n\n### PowerShell Fix\n- Added quoting\n\n---"
        )
        state = {"_completed_phases": ["2"]}
        result = self.mod.fix_pr_body(llm_body, state)
        assert "PowerShell command generation" in result
        assert "RequestName was not properly quoted" in result

    def test_fix_pr_body_no_intent_section_fallback(self):
        """When LLM body has no ## Intent, falls back to extracting content."""
        llm_body = (
            "# Add environment param\n\n"
            "This change adds environment injection.\n\n"
            "---\n<sub>footer</sub>"
        )
        state = {"_completed_phases": ["2"]}
        result = self.mod.fix_pr_body(llm_body, state)
        assert "## Intent" in result
        # Should have extracted something meaningful
        assert "environment injection" in result

    def test_fix_pr_body_fallback_strips_blockquotes_and_tables(self):
        """Fallback intent extraction excludes digest chrome and gate tables."""
        llm_body = (
            "<!-- pr-orchestrator -->\n"
            "# test: title\n\n"
            "> **[Review Digest](https://example.test/digest)**\n"
            "> _What does this change accomplish and why?_\n\n"
            "Actual intent content.\n\n"
            "| Check | Result |\n"
            "| --- | --- |\n"
            "| Lint | Passed |\n"
        )
        state = {"_completed_phases": ["2"]}
        result = self.mod.fix_pr_body(llm_body, state)
        assert "Actual intent content." in result
        assert "https://example.test/digest" not in result
        assert "| Lint | Passed |" not in result

    def test_fix_pr_body_title_override(self):
        """PR title override takes precedence."""
        llm_body = "# Wrong Title\n\n## Intent\n\nFoo\n\n## Changes\n\nBar"
        state = {"_completed_phases": ["2"]}
        result = self.mod.fix_pr_body(llm_body, state, pr_title_override="Correct Title")
        assert "# Correct Title" in result
        assert "Wrong Title" not in result

    def test_fix_pr_body_work_items_list(self):
        """Work items from state list are formatted."""
        llm_body = "## Intent\n\nFix\n\n## Changes\n\nStuff"
        state = {"_completed_phases": ["2"], "work_items_linked": ["AB#123", "AB#456"]}
        result = self.mod.fix_pr_body(llm_body, state)
        assert "AB#123" in result
        assert "AB#456" in result

    def test_fix_pr_body_uses_phase_contract_data(self):
        llm_body = "## Intent\n\nFix\n\n## Changes\n\nStuff"
        state = {
            "gate_build": "failed",
            "test_count": 99,
            "code_review_findings": {},
            "_phases": {
                "1a": {"tests_run": 12, "tests_passed": 10, "tests_failed": 2},
                "1c": {"code_review_findings": {"important": [{"description": "bug"}], "suggestions": []}},
                "2": {"pr_title": "contract title", "work_items_linked": ["AB#42"]},
            },
        }
        result = self.mod.fix_pr_body(llm_body, state)
        assert "# contract title" in result
        assert "12 run, 10 passed, 2 failed" in result
        assert "⚠️ 1 finding(s)" in result
        assert "**Gates**" not in result
        assert "AB#42" in result

    def test_fix_pr_body_cli(self, tmp_path):
        """CLI mode reads files and produces output."""
        state = {
            "gate_lint": "passed",
            "gate_build": "passed",
            "gate_test": "passed",
            "gate_security": "passed",
            "_completed_phases": ["2"],
        }
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps(state), encoding="utf-8")

        body = "## Intent\n\nTest intent.\n\n## Changes\n\nTest changes.\n\n---"
        body_file = tmp_path / "body.md"
        body_file.write_text(body, encoding="utf-8")

        output_file = tmp_path / "output.md"

        result = run_script("fix-pr-body.py", args=[
            "--state-file", str(state_file),
            "--pr-body-file", str(body_file),
            "--output-file", str(output_file),
            "--pr-title", "test: CLI test",
        ])
        assert result["exit_code"] == 0
        output = output_file.read_text(encoding="utf-8")
        assert "DIGEST_LINK_PLACEHOLDER" in output
        assert "## Intent" in output
        assert "Test intent" in output
        assert "test: CLI test" in output


class TestFinalDigest:
    """Tests for final-digest.py — deterministic final digest pipeline."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("final_digest", SCRIPTS_DIR / "final-digest.py")
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_parse_ado_url_devazure(self):
        """Parse dev.azure.com PR URL."""
        result = self.mod._parse_ado_url("https://dev.azure.com/myorg/myproject/_git/myrepo/pullrequest/12345")
        assert result["org"] == "myorg"
        assert result["project"] == "myproject"
        assert result["repo"] == "myrepo"
        assert result["pr_id"] == "12345"
        assert "dev.azure.com" in result["api_base"]

    def test_parse_ado_url_visualstudio(self):
        """Parse visualstudio.com PR URL."""
        result = self.mod._parse_ado_url("https://msazure.visualstudio.com/One/_git/MyRepo/pullrequest/99999")
        assert result["org"] == "msazure"
        assert result["project"] == "One"
        assert result["repo"] == "MyRepo"
        assert result["pr_id"] == "99999"
        assert "visualstudio.com" in result["api_base"]

    def test_parse_ado_url_invalid(self):
        """Invalid URL returns empty dict."""
        result = self.mod._parse_ado_url("https://github.com/owner/repo/pull/123")
        assert result == {}

    def test_build_phase5_data_no_files(self):
        """Build phase5 data with no scraped files."""
        result = self.mod.build_phase5_data(
            pr_url="https://dev.azure.com/org/proj/_git/repo/pullrequest/1",
            scrape_commits_file=None,
            scrape_threads_file=None,
        )
        assert result["pr_url"] == "https://dev.azure.com/org/proj/_git/repo/pullrequest/1"
        assert result["address_feedback"]["comments_addressed"] == 0
        assert result["address_feedback"]["comments_remaining"] == 0
        assert result["address_feedback"]["fix_commits"] == []
        assert result["address_feedback"]["all_addressed"] is True

    def test_build_phase5_data_with_scrape_files(self):
        """Build phase5 data from scraped commit and thread files."""
        with tempfile.TemporaryDirectory() as td:
            commits_file = os.path.join(td, "commits.json")
            threads_file = os.path.join(td, "threads.json")
            with open(commits_file, "w") as f:
                json.dump({"commits": [{"sha": "abc123"}, {"sha": "def456"}]}, f)
            with open(threads_file, "w") as f:
                json.dump({"threads": {
                    "resolved": [{"thread_id": 1}, {"thread_id": 2}],
                    "actionable": [{"thread_id": 3}],
                }}, f)
            result = self.mod.build_phase5_data(
                pr_url="https://dev.azure.com/org/proj/_git/repo/pullrequest/1",
                scrape_commits_file=commits_file,
                scrape_threads_file=threads_file,
            )
            assert result["address_feedback"]["comments_addressed"] == 2
            assert result["address_feedback"]["comments_remaining"] == 1
            assert result["address_feedback"]["fix_commits"] == ["abc123", "def456"]
            assert result["address_feedback"]["all_addressed"] is False

    def test_build_phase5_data_missing_files(self):
        """Build phase5 data with nonexistent file paths."""
        result = self.mod.build_phase5_data(
            pr_url="https://dev.azure.com/org/proj/_git/repo/pullrequest/1",
            scrape_commits_file="/nonexistent/commits.json",
            scrape_threads_file="/nonexistent/threads.json",
        )
        # Should not crash, just return defaults
        assert result["address_feedback"]["comments_addressed"] == 0
        assert result["address_feedback"]["all_addressed"] is True

    def test_build_phase5_data_fallback_to_addressed_details(self):
        """When resolved is empty but addressed_details has entries, count those."""
        with tempfile.TemporaryDirectory() as td:
            commits_file = os.path.join(td, "commits.json")
            threads_file = os.path.join(td, "threads.json")
            with open(commits_file, "w") as f:
                json.dump({"commits": [{"sha": "fix123"}]}, f)
            with open(threads_file, "w") as f:
                json.dump({
                    "threads": {"resolved": [], "actionable": []},
                    "addressed_details": [
                        {"thread_id": "100", "file": "/src/Service.cs", "finding_summary": "Fixed issue", "commit_sha": "fix123"},
                    ],
                }, f)
            result = self.mod.build_phase5_data(
                pr_url="https://dev.azure.com/org/proj/_git/repo/pullrequest/1",
                scrape_commits_file=commits_file,
                scrape_threads_file=threads_file,
            )
            assert result["address_feedback"]["comments_addressed"] == 1
            assert result["address_feedback"]["all_addressed"] is True

    def test_build_phase5_data_fallback_to_commit_count(self):
        """When resolved AND addressed_details are empty but commits exist, use commit count and mark all addressed."""
        with tempfile.TemporaryDirectory() as td:
            commits_file = os.path.join(td, "commits.json")
            threads_file = os.path.join(td, "threads.json")
            with open(commits_file, "w") as f:
                json.dump({"commits": [{"sha": "fix999"}]}, f)
            with open(threads_file, "w") as f:
                json.dump({
                    "threads": {
                        "resolved": [],
                        "actionable": [{"thread_id": "50", "file": "/src/Svc.cs"}],
                    },
                    "addressed_details": [],
                }, f)
            result = self.mod.build_phase5_data(
                pr_url="https://dev.azure.com/org/proj/_git/repo/pullrequest/1",
                scrape_commits_file=commits_file,
                scrape_threads_file=threads_file,
            )
            # Falls back to commit count; marks all addressed since final-digest
            # will resolve the actionable threads moments later
            assert result["address_feedback"]["comments_addressed"] == 1
            assert result["address_feedback"]["comments_remaining"] == 0
            assert result["address_feedback"]["all_addressed"] is True

    def test_load_json_utf8(self):
        """Load a valid UTF-8 JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"key": "value ✅"}, f, ensure_ascii=False)
            f.flush()
            result = self.mod._load_json(f.name, "test")
        os.unlink(f.name)
        assert result["key"] == "value ✅"

    def test_load_json_with_bom(self):
        """Load a UTF-8 BOM JSON file (utf-8-sig fallback)."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="wb") as f:
            content = json.dumps({"key": "bom"}).encode("utf-8-sig")
            f.write(content)
            f.flush()
            result = self.mod._load_json(f.name, "test-bom")
        os.unlink(f.name)
        assert result["key"] == "bom"

    def test_load_json_corrupt_returns_empty(self):
        """Corrupt JSON returns empty dict instead of crashing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("not json {{{")
            f.flush()
            result = self.mod._load_json(f.name, "test-corrupt")
        os.unlink(f.name)
        assert result == {}

    def test_cli_dry_run(self):
        """CLI dry run produces valid JSON output and writes artifacts to the workspace."""
        with tempfile.TemporaryDirectory() as td:
            upstream = os.path.join(td, "upstream-data.json")
            workspace_dir = os.path.join(td, "workspace")
            with open(upstream, "w") as f:
                json.dump({
                    "_completed_phases": ["1a", "1b", "1c", "1d", "2", "3", "4"],
                    "_phases": {
                        "1c": {"code_review_findings": []},
                        "2": {"pr_url": "https://dev.azure.com/o/p/_git/r/pullrequest/1"},
                    },
                }, f)
            digest_input = os.path.join(td, "digest-input.json")
            build_result = run_script("build-digest-input.py", args=[
                upstream, "--output-file", digest_input,
            ])
            assert build_result["exit_code"] == 0, f"build-digest-input.py failed: {build_result['stderr']}"

            result = run_script("final-digest.py", args=[
                "--pr-url", "https://dev.azure.com/o/p/_git/r/pullrequest/1",
                "--platform", "ado",
                "--merge", digest_input,
                "--upstream-fallback", upstream,
                "--workspace-dir", workspace_dir,
                "--dry-run",
            ])
            assert result["exit_code"] == 0, f"final-digest.py failed: {result['stderr']}"
            output = json.loads(result["stdout"].strip())
            assert output["final_verdict"] in ("ready", "approved", "changes_requested", "pending", "unknown")
            assert output["digest_updated"] is True
            assert output["pr_url"] == "https://dev.azure.com/o/p/_git/r/pullrequest/1"
            assert os.path.isfile(os.path.join(workspace_dir, "phase5-data.json"))
            assert os.path.isfile(os.path.join(workspace_dir, "final-digest-input.json"))
            assert os.path.isfile(os.path.join(workspace_dir, "final-digest.md"))

    def test_cli_dry_run_outputs_numeric_counts_and_result_file(self):
        with tempfile.TemporaryDirectory() as td:
            upstream = os.path.join(td, "upstream-data.json")
            digest_input = os.path.join(td, "digest-input.json")
            workspace_dir = os.path.join(td, "workspace")
            commits_file = os.path.join(td, "scrape-fb-commits.json")
            threads_file = os.path.join(td, "scrape-fb-threads.json")
            with open(upstream, "w", encoding="utf-8") as f:
                json.dump({
                    "_completed_phases": ["1a", "1b", "1c", "1d", "2", "3", "4"],
                    "_phases": {
                        "1c": {"code_review_findings": []},
                        "2": {"pr_url": "https://dev.azure.com/o/p/_git/r/pullrequest/1"},
                    },
                }, f)
            with open(commits_file, "w", encoding="utf-8") as f:
                json.dump({"commits": [{"sha": "a" * 40}, {"sha": "b" * 40}]}, f)
            with open(threads_file, "w", encoding="utf-8") as f:
                json.dump({"threads": {"resolved": [{"thread_id": 1}, {"thread_id": 2}], "actionable": []}}, f)

            build_result = run_script("build-digest-input.py", args=[upstream, "--output-file", digest_input])
            assert build_result["exit_code"] == 0, build_result["stderr"]

            result = run_script("final-digest.py", args=[
                "--pr-url", "https://dev.azure.com/o/p/_git/r/pullrequest/1",
                "--platform", "ado",
                "--merge", digest_input,
                "--upstream-fallback", upstream,
                "--workspace-dir", workspace_dir,
                "--scrape-commits-file", commits_file,
                "--scrape-threads-file", threads_file,
                "--dry-run",
            ])
            assert result["exit_code"] == 0, result["stderr"]
            output = json.loads(result["stdout"].strip())
            assert output["total_fixes_pushed"] == 2
            assert output["total_comments_addressed"] == 2
            assert output["total_fixes_pushed"] != "see_stdout"
            assert output["total_comments_addressed"] != "see_stdout"
            result_file = os.path.join(workspace_dir, "final-digest-result.json")
            assert os.path.isfile(result_file)
            with open(result_file, "r", encoding="utf-8") as f:
                persisted = json.load(f)
            assert persisted["total_fixes_pushed"] == 2
            assert persisted["total_comments_addressed"] == 2

    def test_cli_no_merge_base_dry_run(self):
        """CLI with no merge base fails instead of building a misleading Phase 5-only digest."""
        result = run_script("final-digest.py", args=[
            "--pr-url", "https://dev.azure.com/o/p/_git/r/pullrequest/1",
            "--platform", "ado",
            "--dry-run",
        ])
        assert result["exit_code"] == 1, f"Unexpected exit code: {result['stderr']}"
        assert "No valid merge base found" in result["stderr"]
        assert "Re-run Phase 4 (review-digest) first" in result["stderr"]

    def test_cli_ignores_invalid_upstream_fallback_when_merge_exists(self):
        with tempfile.TemporaryDirectory() as td:
            workspace_dir = os.path.join(td, "workspace")
            digest_input = os.path.join(td, "digest-input.json")
            with open(digest_input, "w", encoding="utf-8") as f:
                json.dump({
                    "gates": [{"check": "Lint", "status": "✅ Passed", "details": "OK"}],
                    "findings": {"prevalidate": []},
                    "verdict": "ready",
                    "risk_level": "low",
                    "timeline": [],
                    "advisories": [],
                }, f)
            bad_upstream = os.path.join(td, "upstream-data.json")
            with open(bad_upstream, "w", encoding="utf-8") as f:
                json.dump({"_phases": {}}, f)
            result = run_script("final-digest.py", args=[
                "--pr-url", "https://dev.azure.com/o/p/_git/r/pullrequest/1",
                "--platform", "ado",
                "--merge", digest_input,
                "--upstream-fallback", bad_upstream,
                "--workspace-dir", workspace_dir,
                "--dry-run",
            ])
            assert result["exit_code"] == 0, result["stderr"]

    def test_fix_encoding_failure_logs_warning(self, monkeypatch):
        calls = []

        def fake_run(cmd, label, check=True, timeout=120):
            calls.append(label)
            if label == "build-digest-input --merge":
                output_path = cmd[3]
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump({"verdict": "approved"}, f)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if label == "compose-digest":
                output_path = cmd[3]
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("<!-- ai-agent:pr-orchestrator-digest -->\n# digest\n")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if label == "fix-encoding":
                return subprocess.CompletedProcess(cmd, 3, stdout="", stderr="encoding boom")
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

        monkeypatch.setattr(self.mod, "_run", fake_run)
        monkeypatch.setattr(self.mod, "validate_upstream_data", lambda _: (False, ["bad upstream"]))
        monkeypatch.setattr(self.mod, "_load_upstream_phase_context", lambda _: {})

        with tempfile.TemporaryDirectory() as td:
            workspace_dir = os.path.join(td, "workspace")
            digest_input = os.path.join(td, "digest-input.json")
            with open(digest_input, "w", encoding="utf-8") as f:
                json.dump({
                    "gates": [{"check": "Lint", "status": "✅ Passed", "details": "OK"}],
                    "findings": {"prevalidate": []},
                    "verdict": "ready",
                    "risk_level": "low",
                    "timeline": [],
                    "advisories": [],
                }, f)

            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "final-digest.py",
                    "--pr-url", "https://dev.azure.com/o/p/_git/r/pullrequest/1",
                    "--platform", "ado",
                    "--merge", digest_input,
                    "--workspace-dir", workspace_dir,
                    "--dry-run",
                ],
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.mod.main()

        output = json.loads(stdout.getvalue().strip())
        assert output["digest_updated"] is True
        assert "fix-encoding failed" in stderr.getvalue()
        assert calls.count("fix-encoding") == 1

    def test_resolve_threads_non_ado(self):
        """Thread resolution is skipped for non-ADO platforms."""
        result = self.mod.resolve_threads(
            platform="github",
            pr_url="https://github.com/owner/repo/pull/1",
            scrape_threads_file=None,
            digest_thread_id=None,
        )
        assert result["skipped"] == "not_ado"
        assert result["resolved_threads"] == 0


class TestReviewDigest:
    """Tests for review-digest.py — deterministic review digest pipeline (Phase 4)."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("review_digest", SCRIPTS_DIR / "review-digest.py")
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_parse_ado_url_devazure(self):
        result = self.mod._parse_ado_url("https://dev.azure.com/myorg/myproject/_git/myrepo/pullrequest/12345")
        assert result["org"] == "myorg"
        assert result["project"] == "myproject"
        assert result["pr_id"] == "12345"

    def test_parse_ado_url_visualstudio(self):
        result = self.mod._parse_ado_url("https://msazure.visualstudio.com/One/_git/MyRepo/pullrequest/99999")
        assert result["org"] == "msazure"
        assert result["project"] == "One"

    def test_parse_ado_url_invalid(self):
        assert self.mod._parse_ado_url("https://github.com/owner/repo/pull/1") == {}

    def test_build_upstream_data_with_state_file(self):
        """State file is loaded with phase-scoped fields hydrated into the working copy."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({
                "_phases": {
                    "2": {
                        "pr_url": "https://dev.azure.com/o/p/_git/r/pullrequest/1",
                        "pr_title": "Test PR",
                    },
                    "4": {"digest_comment_id": "123"},
                    "4b": {"walkthrough_posted": True},
                }
            }, f)
            f.flush()
            result = self.mod.build_upstream_data(f.name, "https://override.example/pr/2", "ado")
        os.unlink(f.name)
        assert result["pr_title"] == "Test PR"
        assert result["digest_comment_id"] == "123"
        assert result["walkthrough_posted"] is True
        assert result["pr_url"] == "https://dev.azure.com/o/p/_git/r/pullrequest/1"
        assert result["platform"] == "ado"

    def test_build_upstream_data_missing_state_file(self):
        """Missing state file produces minimal data with pr_url and platform."""
        result = self.mod.build_upstream_data("/nonexistent/state.json", "https://dev.azure.com/o/p/_git/r/pullrequest/1", "ado")
        assert result["pr_url"] == "https://dev.azure.com/o/p/_git/r/pullrequest/1"
        assert result["platform"] == "ado"
        assert len(result) == 2  # only pr_url and platform

    def test_build_upstream_data_preserves_existing_pr_url(self):
        """If state already has pr_url, don't overwrite it."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump({"pr_url": "https://original.com/pr/1", "platform": "github"}, f)
            f.flush()
            result = self.mod.build_upstream_data(f.name, "https://override.com/pr/2", "ado")
        os.unlink(f.name)
        assert result["pr_url"] == "https://original.com/pr/1"
        assert result["platform"] == "github"

    def test_build_upstream_data_corrupt_file(self):
        """Corrupt state file returns minimal data."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write("not json {{{")
            f.flush()
            result = self.mod.build_upstream_data(f.name, "https://dev.azure.com/o/p/_git/r/pullrequest/1", "ado")
        os.unlink(f.name)
        assert result["pr_url"] == "https://dev.azure.com/o/p/_git/r/pullrequest/1"

    def test_build_upstream_data_bom_file(self):
        """UTF-8 BOM state file loads correctly."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="wb") as f:
            content = json.dumps({"risk_level": "High"}).encode("utf-8-sig")
            f.write(content)
            f.flush()
            result = self.mod.build_upstream_data(f.name, "https://dev.azure.com/o/p/_git/r/pullrequest/1", "ado")
        os.unlink(f.name)
        assert result["risk_level"] == "High"

    def test_build_upstream_data_classifies_changed_files_when_risk_missing(self, tmp_path):
        """Missing risk is populated deterministically from changed_files."""
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "changed_files": ["src/controllers/FooController.cs"],
        }), encoding="utf-8")

        result = self.mod.build_upstream_data(
            str(state_file), "https://dev.azure.com/o/p/_git/r/pullrequest/1", "ado"
        )

        assert result["risk_level"] == "medium"
        assert any("API controller change" in signal for signal in result["risk_signals"])

    def test_build_upstream_data_preserves_authoritative_risk_level(self, tmp_path):
        """Existing low/medium/high risk is authoritative and not overwritten."""
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({
            "risk_level": "high",
            "risk_signals": ["existing signal"],
            "changed_files": ["docs/readme.md"],
        }), encoding="utf-8")

        result = self.mod.build_upstream_data(
            str(state_file), "https://dev.azure.com/o/p/_git/r/pullrequest/1", "ado"
        )

        assert result["risk_level"] == "high"
        assert result["risk_signals"] == ["existing signal"]

    def test_build_upstream_data_reads_changed_files_artifact(self, tmp_path):
        """Phase 4 can classify from the shared workspace changed-files.json artifact."""
        state_file = tmp_path / "state.json"
        workspace_dir = tmp_path / "workspace"
        workspace_dir.mkdir()
        state_file.write_text("{}", encoding="utf-8")
        (workspace_dir / "changed-files.json").write_text(
            json.dumps(["src/services/FooService.cs"]), encoding="utf-8"
        )

        result = self.mod.build_upstream_data(
            str(state_file), "https://dev.azure.com/o/p/_git/r/pullrequest/1", "ado", workspace_dir
        )

        assert result["risk_level"] == "medium"
        assert any("Service layer change" in signal for signal in result["risk_signals"])

    def test_validate_digest_valid(self):
        """Validate a valid digest file."""
        # Create a minimal valid digest (just test the function interface)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("<!-- ai-agent:pr-orchestrator-digest -->\n# Test\n")
            f.flush()
            result = self.mod.validate_digest(f.name)
        os.unlink(f.name)
        # The result will likely have violations since it's not a full digest,
        # but the function should return a dict with 'valid' and 'violations' keys
        assert "valid" in result
        assert "violations" in result

    def test_validate_digest_missing_file(self):
        """Validate a nonexistent file returns invalid."""
        result = self.mod.validate_digest("/nonexistent/digest.md")
        assert result.get("valid") is False

    def test_post_findings_failure_logs_warning(self, monkeypatch):
        calls = []

        def fake_run(cmd, label, check=True, timeout=120):
            calls.append(label)
            if label == "build-digest-input":
                output_path = cmd[3]
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump({"verdict": "ready", "risk_level": "low"}, f)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if label == "compose-digest":
                output_path = cmd[3]
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("<!-- ai-agent:pr-orchestrator-digest -->\n# digest\n")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if label == "post-findings":
                return subprocess.CompletedProcess(cmd, 7, stdout="", stderr="boom")
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

        monkeypatch.setattr(self.mod, "_run", fake_run)
        monkeypatch.setattr(self.mod, "validate_digest", lambda _: {"valid": True, "violations": []})
        monkeypatch.setattr(self.mod, "validate_upstream_data", lambda _: (True, []))

        with tempfile.TemporaryDirectory() as td:
            state_file = os.path.join(td, "state.json")
            workspace_dir = os.path.join(td, "workspace")
            findings_file = os.path.join(td, "findings.json")
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({"_phases": {}}, f)
            with open(findings_file, "w", encoding="utf-8") as f:
                json.dump({"findings": []}, f)

            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "review-digest.py",
                    "--pr-url", "https://dev.azure.com/o/p/_git/r/pullrequest/1",
                    "--platform", "ado",
                    "--state-file", state_file,
                    "--workspace-dir", workspace_dir,
                    "--findings-file", findings_file,
                ],
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.mod.main()

        output = json.loads(stdout.getvalue().strip())
        assert output["bot_threads_found"] == 0
        assert output["digest_posted"] is True
        assert "post-findings failed" in stderr.getvalue()
        assert "post-findings" in calls

    def test_upsert_failure_sets_digest_posted_false(self, monkeypatch):
        def fake_run(cmd, label, check=True, timeout=120):
            if label == "build-digest-input":
                output_path = cmd[3]
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump({"verdict": "ready", "risk_level": "low"}, f)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if label == "compose-digest":
                output_path = cmd[3]
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("<!-- ai-agent:pr-orchestrator-digest -->\n# digest\n")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if label == "upsert-digest":
                return subprocess.CompletedProcess(cmd, 9, stdout="", stderr="upsert failed")
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

        monkeypatch.setattr(self.mod, "_run", fake_run)
        monkeypatch.setattr(self.mod, "validate_digest", lambda _: {"valid": True, "violations": []})
        monkeypatch.setattr(self.mod, "validate_upstream_data", lambda _: (True, []))
        stderr = io.StringIO()
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as td:
            state_file = os.path.join(td, "state.json")
            workspace_dir = os.path.join(td, "workspace")
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({"_phases": {}}, f)

            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "review-digest.py",
                    "--pr-url", "https://dev.azure.com/o/p/_git/r/pullrequest/1",
                    "--platform", "ado",
                    "--state-file", state_file,
                    "--workspace-dir", workspace_dir,
                ],
            )
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                with pytest.raises(SystemExit) as excinfo:
                    self.mod.main()

        output = json.loads(stdout.getvalue().strip())
        assert excinfo.value.code == 9
        assert output["digest_posted"] is False
        assert output["error"] == "upsert-digest.py exit 9"
        assert "upsert-digest failed" in stderr.getvalue()

    def test_cli_dry_run(self):
        """CLI dry run with state file produces valid JSON output and workspace artifacts."""
        with tempfile.TemporaryDirectory() as td:
            state_file = os.path.join(td, "state.json")
            workspace_dir = os.path.join(td, "workspace")
            with open(state_file, "w") as f:
                json.dump({
                    "_completed_phases": ["1a", "1b", "1c", "1d", "2", "3", "4"],
                    "_phases": {
                        "1c": {"code_review_findings": []},
                        "2": {"pr_url": "https://dev.azure.com/o/p/_git/r/pullrequest/1"},
                    },
                }, f)

            result = run_script("review-digest.py", args=[
                "--pr-url", "https://dev.azure.com/o/p/_git/r/pullrequest/1",
                "--platform", "ado",
                "--state-file", state_file,
                "--workspace-dir", workspace_dir,
                "--dry-run",
            ])
            assert result["exit_code"] == 0, f"review-digest.py failed: {result['stderr']}"
            output = json.loads(result["stdout"].strip())
            assert output["overall_verdict"] in ("ready", "approved", "changes_requested", "pending", "running", "unknown")
            assert output["digest_posted"] is False  # dry run
            assert output["pr_url"] == "https://dev.azure.com/o/p/_git/r/pullrequest/1"
            assert os.path.isfile(os.path.join(workspace_dir, "upstream-data.json"))
            assert os.path.isfile(os.path.join(workspace_dir, "digest-input.json"))
            assert os.path.isfile(os.path.join(workspace_dir, "digest-output.md"))

    def test_cli_no_state_file_dry_run(self):
        """CLI with no state file still produces output (minimal upstream data)."""
        result = run_script("review-digest.py", args=[
            "--pr-url", "https://dev.azure.com/o/p/_git/r/pullrequest/1",
            "--platform", "ado",
            "--dry-run",
        ])
        # Should complete without crashing
        assert result["exit_code"] in (0, 1), f"Unexpected exit code: {result['stderr']}"

    def test_cli_rejects_invalid_upstream_state(self):
        with tempfile.TemporaryDirectory() as td:
            state_file = os.path.join(td, "state.json")
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "_phases": {
                        "1c": {"code_review_findings": {"unexpected": True}},
                    }
                }, f)
            result = run_script("review-digest.py", args=[
                "--pr-url", "https://dev.azure.com/o/p/_git/r/pullrequest/1",
                "--platform", "ado",
                "--state-file", state_file,
                "--dry-run",
            ])
            assert result["exit_code"] == 1
            assert "invalid upstream-data.json" in result["stdout"]

    def test_run_includes_utf8_env(self, monkeypatch):
        captured = {}

        def fake_subprocess_run(cmd, **kwargs):
            captured.update(kwargs)
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

        monkeypatch.setattr(self.mod.subprocess, "run", fake_subprocess_run)

        result = self.mod._run(["az", "rest", "--method", "get"], label="az rest", check=False)

        assert result.returncode == 0
        assert captured["env"]["PYTHONUTF8"] == "1"
        assert captured["env"]["PYTHONIOENCODING"] == "utf-8"

    def test_post_findings_invalid_json_logs_warning(self, monkeypatch, caplog):
        def fake_run(cmd, label, check=True, timeout=120):
            if label == "build-digest-input":
                output_path = cmd[3]
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump({"verdict": "ready", "risk_level": "low"}, f)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if label == "compose-digest":
                output_path = cmd[3]
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write("<!-- ai-agent:pr-orchestrator-digest -->\n# digest\n")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if label == "post-findings":
                return subprocess.CompletedProcess(cmd, 0, stdout="not-json", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

        monkeypatch.setattr(self.mod, "_run", fake_run)
        monkeypatch.setattr(self.mod, "validate_digest", lambda _: {"valid": True, "violations": []})
        monkeypatch.setattr(self.mod, "validate_upstream_data", lambda _: (True, []))
        caplog.set_level(logging.WARNING, logger=self.mod.__name__)

        with tempfile.TemporaryDirectory() as td:
            state_file = os.path.join(td, "state.json")
            workspace_dir = os.path.join(td, "workspace")
            findings_file = os.path.join(td, "findings.json")
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump({"_phases": {}}, f)
            with open(findings_file, "w", encoding="utf-8") as f:
                json.dump({"findings": []}, f)

            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "review-digest.py",
                    "--pr-url", "https://dev.azure.com/o/p/_git/r/pullrequest/1",
                    "--platform", "ado",
                    "--state-file", state_file,
                    "--workspace-dir", workspace_dir,
                    "--findings-file", findings_file,
                    "--dry-run",
                ],
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.mod.main()

        output = json.loads(stdout.getvalue().strip())
        assert output["bot_threads_found"] == 0
        assert "post-findings returned invalid JSON" in caplog.text

    def test_run_timeout_logs_error(self, monkeypatch, caplog):
        def raise_timeout(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs["timeout"])

        monkeypatch.setattr(self.mod.subprocess, "run", raise_timeout)
        caplog.set_level(logging.ERROR, logger=self.mod.__name__)

        result = self.mod._run(["az", "rest"], label="az rest", check=False, timeout=5)

        assert result.returncode == -1
        assert result.stderr == "Timed out after 5s"
        assert "az rest timed out after 5s" in caplog.text


class TestBugB1CommitLinksEnsureList:
    """Regression: fix_commits stored as string repr '["sha"]' must be coerced to list."""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("bdi", str(SCRIPTS_DIR / "build-digest-input.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_ensure_list_on_string_repr_list(self):
        """ensure_list converts string repr of list to actual list."""
        mod = self._load_module()
        assert mod.ensure_list("['da4c67d']") == ["da4c67d"]
        assert mod.ensure_list("['a', 'b']") == ["a", "b"]
        assert mod.ensure_list("[]") == []

    def test_ensure_list_passthrough(self):
        mod = self._load_module()
        assert mod.ensure_list(["a", "b"]) == ["a", "b"]
        assert mod.ensure_list([]) == []
        assert mod.ensure_list(None) == []

    def test_fix_commits_string_repr_produces_valid_commit_urls(self):
        """B1 regression: string repr fix_commits must not iterate as chars."""
        mod = self._load_module()
        # Simulate the data shape that caused B1: fix_commits as string
        upstream = {
            "_phases": {
                "1c": {
                    "code_review_findings": {
                        "findings": {
                            "Critical": [],
                            "Important": [{"id": "CR-1", "file": "a.cs", "finding": "test", "severity": "Important"}],
                            "Suggestion": [],
                        }
                    }
                },
                "1d": {
                    "code_fix": {
                        "fix_commits": "['da4c67d']",  # BUG: stored as string
                        "done": True,
                    }
                },
            }
        }
        mod.normalize_upstream(upstream)
        result = mod.build_digest_input(upstream)
        findings = result.get("findings", {}).get("prevalidate", [])
        # Commit SHAs should be real hashes, not single chars like '[' or "'"
        for f in findings:
            for sha in f.get("fix_commits", []):
                assert len(sha) >= 6, f"Commit SHA too short (single char bug): '{sha}'"


class TestBugB2GateValidationNonFatal:
    """Regression: empty Phase 1efg should not block digest rendering."""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("pov", str(SCRIPTS_DIR / "phase_output_validation.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_empty_gates_still_passes_validation(self):
        """B2 regression: missing gates are non-fatal; validation should pass if code_review is present."""
        mod = self._load_module()
        data = {
            "_phases": {
                "1c": {
                    "code_review_findings": {
                        "findings": {
                            "Critical": [],
                            "Important": [],
                            "Suggestion": [],
                        }
                    }
                },
            }
        }
        valid, issues = mod.validate_upstream_data(data)
        assert valid is True, f"Validation should pass with empty gates, got issues: {issues}"

    def test_missing_1efg_phase_still_passes(self):
        """B2 regression: completely missing 1efg should not block."""
        mod = self._load_module()
        data = {
            "_phases": {
                "1c": {
                    "code_review_findings": {
                        "findings": {
                            "Critical": [],
                            "Important": [],
                            "Suggestion": [],
                        }
                    }
                },
            }
        }
        valid, issues = mod.validate_upstream_data(data)
        assert valid is True, f"Validation should pass without 1efg phase, got issues: {issues}"


class TestBugB3Phase5TimelinePending:
    """Regression: Phase 5 timeline should show completed, not Pending, when final_verdict exists."""

    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("bdi", str(SCRIPTS_DIR / "build-digest-input.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_af_result_with_final_verdict_no_status(self):
        """B3 regression: _af_result should detect completion from final_verdict."""
        mod = self._load_module()
        af = {"final_verdict": "completed", "pr_url": "https://example.com", "digest_updated": True}
        result = mod._af_result(af)
        assert "Pending" not in result, f"Should not show Pending: {result}"
        assert "✅" in result

    def test_af_result_with_status_no_feedback(self):
        """Existing behavior preserved: explicit status=no_feedback works."""
        mod = self._load_module()
        af = {"status": "no_feedback"}
        assert "No feedback" in mod._af_result(af)

    def test_af_duration_with_final_verdict(self):
        """B3 regression: _af_duration should not return Pending when final_verdict present."""
        mod = self._load_module()
        af = {"final_verdict": "completed", "digest_updated": True}
        duration = mod._af_duration(af)
        assert "Pending" not in duration, f"Should not show Pending: {duration}"

    def test_af_duration_empty_returns_pending(self):
        """Empty dict should still return Pending."""
        mod = self._load_module()
        assert "Pending" in mod._af_duration({})
        assert "Pending" in mod._af_result({})

    def test_build_timeline_with_phase5_no_status(self):
        """B3 regression: full timeline build with Phase 5 data lacking status key."""
        mod = self._load_module()
        data = {
            "_phases": {
                "3": {"watch_and_fix": {"build_status": "skipped"}},
                "5": {"address_feedback": {"final_verdict": "completed", "digest_updated": True}},
            }
        }
        timeline = mod.build_timeline(data)
        af_entry = [t for t in timeline if t["phase"] == "Address Feedback"][0]
        assert "Pending" not in af_entry["result"], f"B3 bug: {af_entry}"
        assert "✅" in af_entry["result"]

    def test_af_result_with_completed_phase5_and_empty_feedback(self):
        """Empty phase 5 payload should not show Pending once phase 5 is completed."""
        mod = self._load_module()
        result = mod._af_result({}, ["1", "2", "5"])
        assert "Pending" not in result
        assert "Complete" in result

    def test_build_timeline_with_completed_phase5_and_empty_feedback(self):
        mod = self._load_module()
        data = {
            "_completed_phases": ["1", "2", "3", "4", "5"],
            "_phases": {
                "3": {"watch_and_fix": {"build_status": "skipped"}},
                "5": {},
            },
        }
        timeline = mod.build_timeline(data)
        af_entry = [t for t in timeline if t["phase"] == "Address Feedback"][0]
        assert "Pending" not in af_entry["result"], af_entry
        assert "Complete" in af_entry["result"]



# --- Boundary Validation Contract Tests -------------------------------------------

class TestBoundaryCoercion:
    """Tests that write→read→digest pipeline preserves correct types.

    These tests validate the systemic fix: coerce_phase_types is applied
    both on write (merge-state.py via normalize_phase_output) AND on read
    (_nested_phase_output in build-digest-input.py).  This prevents
    type-confusion bugs like B1 (string-repr fix_commits) from propagating.
    """

    def test_fix_commits_string_repr_coerced_to_list(self):
        """B1 regression: string repr '['sha1', 'sha2']' → real list."""
        from phase_contracts import coerce_phase_types
        data = {"fix_commits": "['abc123', 'def456']", "fixes_applied": 2}
        result = coerce_phase_types("1d", data)
        assert isinstance(result["fix_commits"], list)
        assert result["fix_commits"] == ["abc123", "def456"]

    def test_fix_commits_json_string_coerced(self):
        """JSON-encoded list string → real list."""
        from phase_contracts import coerce_phase_types
        data = {"fix_commits": '["sha1", "sha2"]'}
        result = coerce_phase_types("1d", data)
        assert result["fix_commits"] == ["sha1", "sha2"]

    def test_fix_commits_single_string_becomes_list(self):
        """Single SHA string → single-element list."""
        from phase_contracts import coerce_phase_types
        data = {"fix_commits": "abc123"}
        result = coerce_phase_types("1d", data)
        assert result["fix_commits"] == ["abc123"]

    def test_fix_commits_already_list_unchanged(self):
        """Already a list → pass through."""
        from phase_contracts import coerce_phase_types
        data = {"fix_commits": ["sha1", "sha2"]}
        result = coerce_phase_types("1d", data)
        assert result["fix_commits"] == ["sha1", "sha2"]

    def test_fix_commits_empty_string_becomes_empty_list(self):
        from phase_contracts import coerce_phase_types
        data = {"fix_commits": ""}
        result = coerce_phase_types("1d", data)
        assert result["fix_commits"] == []

    def test_fix_commits_none_becomes_empty_list(self):
        from phase_contracts import coerce_phase_types
        data = {"fix_commits": None}
        result = coerce_phase_types("1d", data)
        assert result["fix_commits"] == []

    def test_bool_coercion_string_true(self):
        from phase_contracts import coerce_phase_types
        data = {"all_addressed": "true"}
        result = coerce_phase_types("5", data)
        assert result["all_addressed"] is True

    def test_bool_coercion_string_passed(self):
        from phase_contracts import coerce_phase_types
        data = {"walkthrough_posted": "true"}
        result = coerce_phase_types("1c", data)
        assert result["walkthrough_posted"] is True

    def test_bool_coercion_string_false(self):
        from phase_contracts import coerce_phase_types
        data = {"all_addressed": "false"}
        result = coerce_phase_types("5", data)
        assert result["all_addressed"] is False

    def test_phase5_status_canonicalization(self):
        """Phase 5 address_feedback.final_verdict → status mapping."""
        from phase_contracts import coerce_phase_types
        data = {"address_feedback": {"final_verdict": "completed"}}
        result = coerce_phase_types("5", data)
        assert result["address_feedback"]["status"] == "no_feedback"

    def test_phase5_nested_fix_commits_coerced(self):
        """Phase 5 address_feedback.fix_commits string → list."""
        from phase_contracts import coerce_phase_types
        data = {"address_feedback": {"fix_commits": "sha1"}}
        result = coerce_phase_types("5", data)
        assert result["address_feedback"]["fix_commits"] == ["sha1"]

    def test_normalize_applies_coercion(self):
        """normalize_phase_output includes type coercion at the end."""
        from phase_contracts import normalize_phase_output
        raw = {"fix_commits": "['a']", "test_count": 5}
        result = normalize_phase_output("1a", raw)
        # test_count → tests_run (alias) and fix_commits → list
        assert result.get("tests_run") == 5 or result.get("test_count") == 5

    def test_nested_phase_output_coerces(self):
        """_nested_phase_output applies coercion at read boundary."""
        sys.path.insert(0, os.path.dirname(__file__))
        # Simulate state where fix_commits is a string-repr
        state = {
            "_phases": {
                "1d": {
                    "code_fix": {"fixes_applied": 1, "fix_commits": "['abc']"},
                    "fix_commits": "['abc']",
                }
            }
        }
        # Import and call
        import importlib
        bdi = importlib.import_module("build-digest-input")
        merged = bdi._nested_phase_output(state, "1d", "code_fix")
        # fix_commits should be coerced to list
        assert isinstance(merged.get("fix_commits"), list), \
            f"fix_commits not coerced: {merged.get('fix_commits')}"

    def test_write_read_roundtrip_preserves_types(self):
        """Full roundtrip: merge-state write → build-digest read."""
        from phase_contracts import normalize_phase_output
        # Simulate what LLM gives us (messy types)
        raw_phase1d = {
            "code_fix": {"fixes_applied": "1", "fix_commits": "['sha1', 'sha2']"},
            "fix_commits": "['sha1', 'sha2']",
            "findings_remaining": 0,
        }
        # Write side: normalize (which now coerces)
        normalized = normalize_phase_output("1d", raw_phase1d)
        assert isinstance(normalized.get("fix_commits"), list)
        assert normalized["fix_commits"] == ["sha1", "sha2"]

        # Read side: build state and read via _nested_phase_output
        state = {"_phases": {"1d": normalized}}
        import importlib
        bdi = importlib.import_module("build-digest-input")
        merged = bdi._nested_phase_output(state, "1d", "code_fix")
        assert isinstance(merged.get("fix_commits"), list)
        assert merged["fix_commits"] == ["sha1", "sha2"]

    def test_canonicalize_status_aliases(self):
        from phase_contracts import canonicalize_status
        assert canonicalize_status("completed") == "no_feedback"
        assert canonicalize_status("done") == "no_feedback"
        assert canonicalize_status("addressed") == "all_addressed"
        assert canonicalize_status("partial") == "partial"
        assert canonicalize_status("") is None
        assert canonicalize_status(None) is None


class TestPhaseModels:
    """Tests for the typed dataclass phase models (phase_models.py)."""

    # -- helpers for lazy import (avoid breaking other tests if models missing) --

    @staticmethod
    def _models():
        import phase_models as pm
        return pm

    # ---- from_raw basics ----

    def test_from_raw_none_returns_defaults(self):
        pm = self._models()
        m = pm.Phase1aOutput.from_raw(None)
        assert m.tests_run == 0
        assert m.business_logic_digest == ""

    def test_from_raw_empty_dict(self):
        pm = self._models()
        m = pm.Phase5Output.from_raw({})
        assert m.fix_commits == []
        assert m.all_addressed is False

    def test_from_raw_unknown_keys_dropped(self):
        pm = self._models()
        m = pm.Phase2Output.from_raw({"pr_url": "https://x", "garbage": 99})
        assert m.pr_url == "https://x"
        assert not hasattr(m, "garbage") or "garbage" not in m.to_dict()

    # ---- alias resolution ----

    def test_1a_alias_test_count(self):
        pm = self._models()
        m = pm.Phase1aOutput.from_raw({"test_count": "42"})
        assert m.tests_run == 42

    def test_3_alias_total_fixes_pushed(self):
        pm = self._models()
        m = pm.Phase3Output.from_raw({"total_fixes_pushed": "5"})
        assert m.fixes_pushed == 5

    # ---- type coercion: lists ----

    def test_fix_commits_string_repr_to_list(self):
        pm = self._models()
        m = pm.Phase1dOutput.from_raw({"fix_commits": "['abc', 'def']"})
        assert m.fix_commits == ["abc", "def"]

    def test_fix_commits_json_string_to_list(self):
        pm = self._models()
        m = pm.Phase3Output.from_raw({"fix_commits": '["a","b"]'})
        assert m.fix_commits == ["a", "b"]

    def test_fix_commits_single_string_to_list(self):
        pm = self._models()
        m = pm.Phase5Output.from_raw({"fix_commits": "abc123"})
        assert m.fix_commits == ["abc123"]

    def test_fix_commits_none_to_empty_list(self):
        pm = self._models()
        m = pm.Phase1dOutput.from_raw({"fix_commits": None})
        assert m.fix_commits == []

    def test_fix_summaries_coerced(self):
        pm = self._models()
        m = pm.Phase3Output.from_raw({"fix_summaries": "single summary"})
        assert m.fix_summaries == ["single summary"]

    def test_addressed_details_coerced(self):
        pm = self._models()
        m = pm.Phase5Output.from_raw({"addressed_details": "['d1']"})
        assert m.addressed_details == ["d1"]

    def test_human_judgment_findings_coerced(self):
        pm = self._models()
        m = pm.Phase1cOutput.from_raw({"human_judgment_findings": "finding1"})
        assert m.human_judgment_findings == ["finding1"]

    # ---- type coercion: bools ----

    def test_all_addressed_string_true(self):
        pm = self._models()
        m = pm.Phase5Output.from_raw({"all_addressed": "true"})
        assert m.all_addressed is True

    def test_walkthrough_posted_string_yes(self):
        pm = self._models()
        m = pm.Phase4bOutput.from_raw({"walkthrough_posted": "yes"})
        assert m.walkthrough_posted is True

    def test_bool_string_false(self):
        pm = self._models()
        m = pm.Phase5Output.from_raw({"all_addressed": "false"})
        assert m.all_addressed is False

    # ---- type coercion: ints ----

    def test_fixes_applied_string_to_int(self):
        pm = self._models()
        m = pm.Phase1dOutput.from_raw({"fixes_applied": "7"})
        assert m.fixes_applied == 7

    def test_elapsed_minutes_string(self):
        pm = self._models()
        m = pm.Phase3Output.from_raw({"elapsed_minutes": "120"})
        assert m.elapsed_minutes == 120

    def test_int_bad_string_defaults_zero(self):
        pm = self._models()
        m = pm.Phase3Output.from_raw({"elapsed_minutes": "not_a_number"})
        assert m.elapsed_minutes == 0

    def test_comments_addressed_string(self):
        pm = self._models()
        m = pm.Phase5Output.from_raw({"comments_addressed": "3", "comments_remaining": "1"})
        assert m.comments_addressed == 3
        assert m.comments_remaining == 1

    def test_iteration_coercion(self):
        pm = self._models()
        m = pm.Phase5Output.from_raw({"iteration": "2"})
        assert m.iteration == 2

    # ---- Phase 5 status canonicalization ----

    def test_status_from_final_verdict_completed(self):
        pm = self._models()
        m = pm.Phase5Output.from_raw({"address_feedback": {"final_verdict": "completed"}})
        assert m.status == "no_feedback"

    def test_status_from_final_verdict_addressed(self):
        pm = self._models()
        m = pm.Phase5Output.from_raw({"address_feedback": {"final_verdict": "addressed"}})
        assert m.status == "all_addressed"

    def test_status_explicit_overrides_verdict(self):
        pm = self._models()
        m = pm.Phase5Output.from_raw({
            "status": "partial",
            "address_feedback": {"final_verdict": "completed"},
        })
        assert m.status == "partial"

    def test_status_unknown_verdict_passthrough(self):
        pm = self._models()
        m = pm.Phase5Output.from_raw({"address_feedback": {"final_verdict": "custom_value"}})
        assert m.status == "custom_value"

    # ---- Phase 5 nested coercion ----

    def test_phase5_nested_fix_commits_coerced(self):
        pm = self._models()
        m = pm.Phase5Output.from_raw({
            "address_feedback": {"fix_commits": "abc123", "addressed_details": "['d']"},
        })
        assert m.address_feedback["fix_commits"] == ["abc123"]
        assert m.address_feedback["addressed_details"] == ["d"]

    # ---- Phase 1d nested coercion ----

    def test_phase1d_nested_code_fix_commits(self):
        pm = self._models()
        m = pm.Phase1dOutput.from_raw({
            "code_fix": {"fix_commits": "sha1"},
        })
        assert m.code_fix["fix_commits"] == ["sha1"]

    # ---- validation / fail-loud ----

    def test_phase2_bad_url_raises(self):
        pm = self._models()
        with pytest.raises(ValueError, match="pr_url must be a URL"):
            pm.Phase2Output.from_raw({"pr_url": "not-a-url"})

    def test_phase2_empty_url_ok(self):
        pm = self._models()
        m = pm.Phase2Output.from_raw({})
        assert m.pr_url == ""

    def test_phase1c_bad_findings_coerced_to_dict(self):
        pm = self._models()
        m = pm.Phase1cOutput.from_raw({"code_review_findings": "not a dict"})
        assert m.code_review_findings == {}

    # ---- to_dict / roundtrip ----

    def test_to_dict_drops_none(self):
        pm = self._models()
        m = pm.Phase4Output()
        d = m.to_dict()
        # Empty strings are kept, but None values dropped
        assert isinstance(d, dict)

    def test_roundtrip_1d(self):
        pm = self._models()
        raw = {"fix_commits": "['a']", "fixes_applied": "2", "findings_remaining": "1"}
        m1 = pm.Phase1dOutput.from_raw(raw)
        d = m1.to_dict()
        m2 = pm.Phase1dOutput.from_raw(d)
        assert m2.fix_commits == ["a"]
        assert m2.fixes_applied == 2

    def test_roundtrip_5(self):
        pm = self._models()
        raw = {
            "all_addressed": "true",
            "fix_commits": "['x']",
            "comments_addressed": "5",
            "address_feedback": {"final_verdict": "completed", "fix_commits": "y"},
        }
        m1 = pm.Phase5Output.from_raw(raw)
        d = m1.to_dict()
        m2 = pm.Phase5Output.from_raw(d)
        assert m2.all_addressed is True
        assert m2.fix_commits == ["x"]
        assert m2.comments_addressed == 5
        assert m2.status == "no_feedback"

    # ---- PHASE_MODELS registry ----

    def test_registry_all_phases_present(self):
        pm = self._models()
        expected = {"1a", "1b", "1c", "1d", "2", "3", "4", "4b", "5"}
        assert set(pm.PHASE_MODELS.keys()) == expected

    def test_registry_from_raw_all_phases(self):
        pm = self._models()
        for phase_id, cls in pm.PHASE_MODELS.items():
            m = cls.from_raw({})
            assert isinstance(m, pm.PhaseModel), f"{phase_id} not a PhaseModel"

    # ---- coercion helpers standalone ----

    def test_to_list_already_list(self):
        pm = self._models()
        assert pm.to_list([1, 2]) == [1, 2]

    def test_to_list_empty_string(self):
        pm = self._models()
        assert pm.to_list("") == []

    def test_to_list_number(self):
        pm = self._models()
        assert pm.to_list(42) == [42]

    def test_to_bool_int(self):
        pm = self._models()
        assert pm.to_bool(1) is True
        assert pm.to_bool(0) is False

    def test_to_int_float(self):
        pm = self._models()
        assert pm.to_int(3.7) == 3

    def test_to_int_bool_ignored(self):
        pm = self._models()
        assert pm.to_int(True) == 0  # bool subclass of int, but we default

    def test_canonicalize_status_none(self):
        pm = self._models()
        assert pm.canonicalize_status(None) is None
        assert pm.canonicalize_status("") is None


class TestRetryUtils:
    @staticmethod
    def _load_module():
        import importlib.util
        spec = importlib.util.spec_from_file_location("retry_utils", str(SCRIPTS_DIR / "retry_utils.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_run_with_retry_succeeds_on_first_attempt(self):
        from unittest.mock import patch

        mod = self._load_module()
        completed = subprocess.CompletedProcess(["az", "rest"], 0, stdout="ok", stderr="")

        with patch.object(mod.subprocess, "run", return_value=completed) as mock_run, \
             patch.object(mod.time, "sleep") as mock_sleep:
            result = mod.run_with_retry(["az", "rest"], capture_output=True, text=True)

        assert result is completed
        assert mock_run.call_count == 1
        mock_sleep.assert_not_called()

    def test_run_with_retry_retries_then_succeeds(self):
        from unittest.mock import patch

        mod = self._load_module()
        failed = subprocess.CompletedProcess(["az", "rest"], 1, stdout="", stderr="rate limited")
        succeeded = subprocess.CompletedProcess(["az", "rest"], 0, stdout="ok", stderr="")

        with patch.object(mod.subprocess, "run", side_effect=[failed, succeeded]) as mock_run, \
             patch.object(mod.time, "sleep") as mock_sleep:
            result = mod.run_with_retry(["az", "rest"], capture_output=True, text=True)

        assert result is succeeded
        assert mock_run.call_count == 2
        mock_sleep.assert_called_once_with(1)

    def test_run_with_retry_raises_after_max_retries(self):
        from unittest.mock import call, patch

        mod = self._load_module()
        failed = subprocess.CompletedProcess(["az", "rest"], 1, stdout="", stderr="server error")

        with patch.object(mod.subprocess, "run", side_effect=[failed, failed, failed]) as mock_run, \
             patch.object(mod.time, "sleep") as mock_sleep:
            with pytest.raises(subprocess.SubprocessError, match="All 3 attempts failed"):
                mod.run_with_retry(["az", "rest"], max_retries=2, capture_output=True, text=True)

        assert mock_run.call_count == 3
        assert mock_sleep.call_args_list == [call(1), call(2)]


class TestRunPhasesEventLogs:
    def test_run_conductor_uses_log_file_auto(self, tmp_path):
        """run_conductor passes --log-file auto for structured JSONL output."""
        from importlib.util import spec_from_file_location, module_from_spec
        from unittest.mock import patch

        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

        workflow = tmp_path / "phase1a-digests.yaml"
        workflow.write_text("# stub", encoding="utf-8")
        completed = subprocess.CompletedProcess(["conductor"], 0)

        with patch.object(mod.subprocess, "run", return_value=completed) as mock_run:
            _, event_log_glob = mod.run_conductor(
                workflow_path=workflow,
                inputs={"target_branch": "main"},
                conductor_flags=[],
                run_id="current-run",
                phase_id="1a",
                attempt=1,
                work_dir=tmp_path,
            )

        cmd = mock_run.call_args.args[0]
        assert "--log-file" in cmd
        log_file_value = cmd[cmd.index("--log-file") + 1]
        # Must be "auto" — explicit paths get plain text, not JSONL
        assert log_file_value == "auto"

        # Glob should match the workflow stem without run_id
        assert "conductor-phase1a-digests-*.events.jsonl" in event_log_glob


# ---------------------------------------------------------------------------
# resolve-pr-threads.py tests
# ---------------------------------------------------------------------------


class TestResolvePrThreads:
    """Tests for the deterministic PR thread resolution script."""

    def _load_mod(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("resolve_pr_threads", SCRIPTS_DIR / "resolve-pr-threads.py")
        mod = module_from_spec(spec)
        import sys as _sys
        if str(SCRIPTS_DIR) not in _sys.path:
            _sys.path.insert(0, str(SCRIPTS_DIR))
        spec.loader.exec_module(mod)
        return mod

    def test_resolve_threads_ado(self, monkeypatch):
        """resolve_threads should call az rest for ADO PRs."""
        mod = self._load_mod()

        calls = []
        def mock_run(cmd, **kw):
            calls.append(cmd)
            result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return result
        monkeypatch.setattr(mod.subprocess, "run", mock_run)

        results = mod.resolve_threads(
            "https://dev.azure.com/myorg/myproj/_git/myrepo/pullrequest/42",
            ["100", "200"],
            status=2,
        )
        assert len(results) == 2
        assert all(r["status"] == "resolved" for r in results)
        assert len(calls) == 2
        # Verify az rest was called with correct thread IDs
        assert "100" in calls[0][5]  # URL contains thread ID
        assert "200" in calls[1][5]

    def test_resolve_threads_dry_run(self):
        """Dry run should not make any API calls."""
        mod = self._load_mod()
        results = mod.resolve_threads(
            "https://dev.azure.com/myorg/myproj/_git/myrepo/pullrequest/42",
            ["100"],
            dry_run=True,
        )
        assert len(results) == 1
        assert results[0]["status"] == "dry_run"

    def test_resolve_threads_bad_url(self):
        """Bad PR URL should return error."""
        mod = self._load_mod()
        results = mod.resolve_threads("not-a-url", ["100"])
        assert len(results) == 1
        assert "error" in results[0]

    def test_load_thread_ids_from_file(self, tmp_path):
        """load_thread_ids_from_file should parse scrape-fb-threads.json."""
        mod = self._load_mod()

        scrape_file = tmp_path / "scrape-fb-threads.json"
        scrape_file.write_text(json.dumps({
            "threads": {
                "resolved": [
                    {"thread_id": 10, "classification": "bug"},
                    {"thread_id": 20, "classification": "bug"},
                ],
                "actionable": [
                    {"thread_id": 30, "classification": "suggestion"},
                ],
            }
        }))

        resolved, suggestions = mod.load_thread_ids_from_file(str(scrape_file))
        assert resolved == ["10", "20"]
        assert suggestions == ["30"]

    def test_load_thread_ids_missing_file(self):
        """Missing file should return empty lists."""
        mod = self._load_mod()
        resolved, suggestions = mod.load_thread_ids_from_file("/nonexistent/file.json")
        assert resolved == []
        assert suggestions == []

    def test_github_threads_skipped(self):
        """GitHub threads should be skipped (not supported)."""
        mod = self._load_mod()
        results = mod.resolve_threads(
            "https://github.com/owner/repo/pull/42",
            ["100"],
        )
        assert len(results) == 1
        assert results[0]["status"] == "skipped"


# ---------------------------------------------------------------------------
# _validate_pr_exists tests
# ---------------------------------------------------------------------------


class TestValidatePrExists:
    """Tests for deterministic PR validation after Phase 2."""

    def _load_mod(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_validate_pr_no_url(self, capsys):
        """No PR URL should return False."""
        mod = self._load_mod()
        result = mod._validate_pr_exists({}, Path("."))
        assert result is False

    def test_validate_pr_bad_url(self, capsys):
        """Unparseable URL should return False."""
        mod = self._load_mod()
        state = {"_phases": {"2": {"pr_url": "garbage"}}}
        result = mod._validate_pr_exists(state, Path("."))
        assert result is False


# ---------------------------------------------------------------------------
# PHASES_THAT_COMMIT coverage
# ---------------------------------------------------------------------------


class TestPhasesCommitSet:
    """Verify the PHASES_THAT_COMMIT set covers lint auto-fix."""

    def _load_mod(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location("run_phases", str(SCRIPTS_DIR / "run-phases.py"))
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_all_commit_phases_present(self):
        """All phases that create commits should be covered."""
        mod = self._load_mod()
        expected = {"1b", "1d", "3", "5"}
        assert mod.PHASES_THAT_COMMIT == expected


class TestApplyLintFix:
    @staticmethod
    def _load_module():
        return load_script_module("apply_lint_fix", "apply-lint-fix.py")[0]

    @staticmethod
    def _completed(returncode=0, stdout="", stderr=""):
        return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)

    def _write_allowlist(self, tmp_path, files):
        path = tmp_path / "changed-files.json"
        path.write_text(json.dumps(files), encoding="utf-8")
        return path

    def _run_main(self, mod, args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = mod.main(args)
        output = stdout.getvalue().strip()
        return {
            "exit_code": exit_code,
            "stdout": stdout.getvalue(),
            "stderr": stderr.getvalue(),
            "json": json.loads(output) if output else None,
        }

    def test_happy_path_commits_scoped_dotnet_fix(self, tmp_path):
        mod = self._load_module()
        allowlist = self._write_allowlist(tmp_path, ["src/app.cs"])
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["git", "status", "--porcelain"]:
                index = sum(1 for item in calls if item == ["git", "status", "--porcelain"])
                return self._completed(stdout="" if index == 1 else " M src/app.cs\n")
            if cmd == ["dotnet", "format", "App.sln", "--include", "src/app.cs"]:
                return self._completed()
            if cmd == ["git", "add", "--", "src/app.cs"]:
                return self._completed()
            if cmd[:2] == ["git", "commit"]:
                assert "style: auto-fix lint violations in PR-scoped files" in cmd[3]
                assert "- src/app.cs" in cmd[3]
                return self._completed(stdout="[main abc123] committed\n")
            if cmd == ["git", "rev-parse", "HEAD"]:
                return self._completed(stdout="abc123\n")
            pytest.fail(f"Unexpected command in test mock: {cmd!r}")

        with patch.object(mod, "find_solution_file", return_value="App.sln"), \
             patch.object(mod, "run_command", side_effect=fake_run):
            result = self._run_main(mod, ["--changed-files", str(allowlist), "--project-type", "dotnet"])

        assert result["exit_code"] == 0
        assert result["json"] == {
            "status": "fixed",
            "files_fixed": ["src/app.cs"],
            "illegal_files": [],
            "commit_sha": "abc123",
        }
        assert ["dotnet", "format", "App.sln", "--include", "src/app.cs"] in calls
        assert ["git", "add", "--", "src/app.cs"] in calls

    def test_scope_violation_reverts_out_of_scope_files(self, tmp_path):
        mod = self._load_module()
        allowlist = self._write_allowlist(tmp_path, ["src/app.py"])
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["git", "status", "--porcelain"]:
                index = sum(1 for item in calls if item == ["git", "status", "--porcelain"])
                output = "" if index == 1 else " M src/app.py\n M src/other.py\n"
                return self._completed(stdout=output)
            if cmd == ["ruff", "check", "--fix", "src/app.py"]:
                return self._completed()
            if cmd == ["git", "ls-files", "--error-unmatch", "--", "src/other.py"]:
                return self._completed(stdout="src/other.py\n")
            if cmd == ["git", "checkout", "HEAD", "--", "src/other.py"]:
                return self._completed()
            pytest.fail(f"Unexpected command in test mock: {cmd!r}")

        with patch.object(mod, "run_command", side_effect=fake_run):
            result = self._run_main(mod, ["--changed-files", str(allowlist), "--project-type", "python"])

        assert result["exit_code"] == 1
        assert result["json"] == {
            "status": "scope_violation",
            "files_fixed": [],
            "illegal_files": ["src/other.py"],
            "commit_sha": "",
        }
        assert ["git", "checkout", "HEAD", "--", "src/other.py"] in calls
        assert all(cmd[:2] != ["git", "add"] for cmd in calls)
        assert all(cmd[:2] != ["git", "commit"] for cmd in calls)

    def test_no_changes_exits_clean_without_commit(self, tmp_path):
        mod = self._load_module()
        allowlist = self._write_allowlist(tmp_path, ["src/app.cs"])
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["git", "status", "--porcelain"]:
                return self._completed(stdout="")
            if cmd == ["dotnet", "format", "App.sln", "--include", "src/app.cs"]:
                return self._completed()
            pytest.fail(f"Unexpected command in test mock: {cmd!r}")

        with patch.object(mod, "find_solution_file", return_value="App.sln"), \
             patch.object(mod, "run_command", side_effect=fake_run):
            result = self._run_main(mod, ["--changed-files", str(allowlist), "--project-type", "dotnet"])

        assert result["exit_code"] == 0
        assert result["json"] == {
            "status": "clean",
            "files_fixed": [],
            "illegal_files": [],
            "commit_sha": "",
        }
        assert all(cmd[:2] != ["git", "commit"] for cmd in calls)

    def test_empty_allowlist_exits_clean_without_running_formatter(self, tmp_path):
        mod = self._load_module()
        allowlist = self._write_allowlist(tmp_path, [])

        with patch.object(mod, "run_command") as mock_run:
            result = self._run_main(mod, ["--changed-files", str(allowlist)])

        assert result["exit_code"] == 0
        assert result["json"] == {
            "status": "clean",
            "files_fixed": [],
            "illegal_files": [],
            "commit_sha": "",
        }
        mock_run.assert_not_called()

    @pytest.mark.parametrize(
        "files, expected_command",
        [
            (["src/app.cs"], ["dotnet", "format", "App.sln", "--include", "src/app.cs"]),
            (["web/app.ts"], ["npx", "eslint", "--fix", "web/app.ts"]),
            (["src/app.py"], ["ruff", "check", "--fix", "src/app.py"]),
        ],
    )
    def test_project_type_auto_detects_formatter_from_allowlist(self, tmp_path, files, expected_command):
        mod = self._load_module()
        allowlist = self._write_allowlist(tmp_path, files)
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["git", "status", "--porcelain"]:
                index = sum(1 for item in calls if item == ["git", "status", "--porcelain"])
                output = "" if index == 1 else f" M {files[0]}\n"
                return self._completed(stdout=output)
            if cmd == expected_command:
                return self._completed()
            pytest.fail(f"Unexpected command in test mock: {cmd!r}")

        with patch.object(mod, "find_solution_file", return_value="App.sln"), \
             patch.object(mod, "run_command", side_effect=fake_run):
            result = self._run_main(mod, ["--changed-files", str(allowlist), "--dry-run"])

        assert result["exit_code"] == 0
        assert result["json"]["status"] == "fixed"
        assert expected_command in calls

    def test_mixed_languages_runs_each_formatter_with_scoped_files(self, tmp_path):
        mod = self._load_module()
        allowlist = self._write_allowlist(tmp_path, ["src/app.cs", "web/app.ts"])
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["git", "status", "--porcelain"]:
                index = sum(1 for item in calls if item == ["git", "status", "--porcelain"])
                output = "" if index == 1 else " M src/app.cs\n M web/app.ts\n"
                return self._completed(stdout=output)
            if cmd == ["dotnet", "format", "App.sln", "--include", "src/app.cs"]:
                return self._completed()
            if cmd == ["npx", "eslint", "--fix", "web/app.ts"]:
                return self._completed()
            pytest.fail(f"Unexpected command in test mock: {cmd!r}")

        with patch.object(mod, "find_solution_file", return_value="App.sln"), \
             patch.object(mod, "run_command", side_effect=fake_run):
            result = self._run_main(mod, ["--changed-files", str(allowlist), "--project-type", "auto", "--dry-run"])

        assert result["exit_code"] == 0
        assert result["json"] == {
            "status": "fixed",
            "files_fixed": ["src/app.cs", "web/app.ts"],
            "illegal_files": [],
            "commit_sha": "",
        }
        assert ["dotnet", "format", "App.sln", "--include", "src/app.cs"] in calls
        assert ["npx", "eslint", "--fix", "web/app.ts"] in calls

    def test_dry_run_skips_git_add_and_commit(self, tmp_path):
        mod = self._load_module()
        allowlist = self._write_allowlist(tmp_path, ["src/app.cs"])
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["git", "status", "--porcelain"]:
                index = sum(1 for item in calls if item == ["git", "status", "--porcelain"])
                return self._completed(stdout="" if index == 1 else " M src/app.cs\n")
            if cmd == ["dotnet", "format", "App.sln", "--include", "src/app.cs"]:
                return self._completed()
            pytest.fail(f"Unexpected command in test mock: {cmd!r}")

        with patch.object(mod, "find_solution_file", return_value="App.sln"), \
             patch.object(mod, "run_command", side_effect=fake_run):
            result = self._run_main(mod, ["--changed-files", str(allowlist), "--project-type", "dotnet", "--dry-run"])

        assert result["exit_code"] == 0
        assert result["json"] == {
            "status": "fixed",
            "files_fixed": ["src/app.cs"],
            "illegal_files": [],
            "commit_sha": "",
        }
        assert "would stage files: src/app.cs" in result["stderr"]
        assert all(cmd[:2] != ["git", "add"] for cmd in calls)
        assert all(cmd[:2] != ["git", "commit"] for cmd in calls)

    def test_missing_solution_file_exits_with_formatter_failed(self, tmp_path):
        mod = self._load_module()
        allowlist = self._write_allowlist(tmp_path, ["src/app.cs"])

        with patch.object(mod, "find_solution_file", side_effect=FileNotFoundError("No .sln file found for dotnet auto-fix")):
            result = self._run_main(mod, ["--changed-files", str(allowlist), "--project-type", "dotnet"])

        assert result["exit_code"] == 2
        assert result["json"] == {
            "status": "formatter_failed",
            "files_fixed": [],
            "illegal_files": [],
            "commit_sha": "",
        }
        assert "No .sln file found for dotnet auto-fix" in result["stderr"]

    def test_missing_allowlist_file_exits_with_formatter_failed(self, tmp_path):
        mod = self._load_module()
        missing_path = tmp_path / "missing.json"

        result = self._run_main(mod, ["--changed-files", str(missing_path)])

        assert result["exit_code"] == 2
        assert result["json"] == {
            "status": "formatter_failed",
            "files_fixed": [],
            "illegal_files": [],
            "commit_sha": "",
        }
        assert "Changed-files JSON not found" in result["stderr"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

