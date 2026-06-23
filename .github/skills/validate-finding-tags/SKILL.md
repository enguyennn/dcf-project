---
name: validate-finding-tags
description: "Deterministic post-review validator that drops doc-backed findings whose 'tag' cannot be verified as an inline [GK-*-N] rule tag in the cited 'guideline' document. Deep-reasoning findings (guideline: \"deep-reasoning\", tag: \"DEEPREASONING\") are always kept. Used by reviewer agents (currently the DomainReviewer)."
user-invocable: false
---

# validate-finding-tags

Deterministic Python script invoked by reviewer agents **after** they `INSERT INTO
gk_review_results` and **before** they `UPDATE gk_batches SET status = 'reviewed'`.

Findings are grounded two ways:

- **Deep-reasoning findings** cite the reserved guideline `"deep-reasoning"` and carry the
  tag `"DEEPREASONING"`. They are always kept — this is the only non-`[GK-*-N]` path.
- **Doc-backed findings** cite the full file path of a guideline doc. The script verifies
  that the finding cites a real guideline doc which contains a real
  `[GK-<PREFIX>-<NUMBER>]` rule tag matching the violation's `tag`. Findings that fail any
  check are moved from `violations` into `dropped_findings` with a structured
  `drop_reason`.

This is the deterministic safety net behind §2.2 of the Gatekeeper V2 design
("Findings with unknown guideline or tag values are dropped").

## Usage

The implementation is [`scripts/validate_finding_tags.py`](scripts/validate_finding_tags.py).

```bash
python validate_finding_tags.py \
  --batch-id <batch_id> \
  --repo <repo_path> \
  [--skills-root <skills_path>] \
  [--db <sqlite_path>]
```

- `--batch-id` *(required)*: the batch ID whose `gk_review_results` row to validate.
- `--repo` *(required)*: absolute path to the repository root; used when resolving
  repo-relative `guideline` paths.
- `--skills-root` *(optional)*: absolute path to the skills root (usually
  `<repo>/.github/skills`). Defaults to `<repo>/.github/skills`.
- `--db` *(optional)*: path to the session SQLite database. Defaults to the value of
  the `GK_SESSION_DB` environment variable.

## Behavior

For each violation:

1. If `violation["guideline"]` is the reserved sentinel `"deep-reasoning"` or
   `violation["tag"]` is `"DEEPREASONING"` → kept (deep-reasoning findings are always allowed).
2. Otherwise resolve `violation["guideline"]` against, in order: absolute path, then
   `<repo>/<guideline>`, then `<skills-root>/<guideline>`.
3. If the path doesn't resolve to an existing file → drop with
   `drop_reason: "guideline-doc-missing"`.
4. Read the file and extract every inline tag matching `\[(GK-[A-Z0-9]+-\d+)\]`.
5. If no tags are present in the file → drop with `drop_reason: "guideline-untagged"`.
6. Read `violation["tag"]`.
   - Missing/empty → drop with `drop_reason: "missing-tag"`.
   - Doesn't match `^GK-[A-Z0-9]+-\d+$` → drop with `drop_reason: "malformed-tag"`.
   - Not present in the tag set extracted from the doc → drop with
     `drop_reason: "tag-not-found"`.
7. Otherwise → kept.

The script rewrites the same row's `violations` and `dropped_findings` JSON columns
atomically in a single `UPDATE`.

### `dropped_findings` entry shape

Each new dropped entry has:

```json
{
  "file": "<violation.file_name>",
  "line": "<violation.startline or null>",
  "suspected_issue": "<violation.violation or violation.detection>",
  "drop_reason": "<one of the drop reasons above>",
  "detail": "<short human-readable explanation>"
}
```

### Idempotency

Re-running the script on an already-validated row is a no-op: validations are
re-applied against the (already pruned) `violations` array, and previously dropped
findings are not re-evaluated.

## Output

Prints a single JSON object to stdout:

```json
{
  "batch_id": "abc123",
  "kept": 4,
  "dropped": 3,
  "drops_by_reason": {
    "guideline-untagged": 2,
    "tag-not-found": 1
  }
}
```

## Exit Codes

- `0` on success (drops are normal — a row with zero kept findings is still a success).
- Non-zero only on IO / SQL / JSON errors (e.g. missing DB, malformed `violations`
  JSON in the row, batch not found).
