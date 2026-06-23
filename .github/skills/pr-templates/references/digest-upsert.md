# Digest Comment Upsert Pattern

> Reference for posting and updating the PR Orchestrator Review Digest comment.
> Used by: ReviewDigest (Phase 4), AddressReviewFeedback (Phase 5), Final Digest Refresh (Step 6 of Interactive/Yolo pipelines).

Adapted from [agent-governance-toolkit](https://github.com/microsoft/agent-governance-toolkit) and [ai-native-team](https://github.com/azure-core/ai-native-team). To avoid "wall of bot comments":

1. Include an HTML marker at the top of every digest comment body: `<!-- ai-agent:pr-orchestrator-digest -->`
2. Before posting, search existing PR comments for this marker
3. If found → **UPDATE** the existing comment with new content (see ADO Update Pattern below)
4. If not found → **CREATE** a new comment

This ensures re-running Phase 4 updates the existing digest rather than creating duplicates. The marker is invisible to readers but uniquely identifies the digest comment for programmatic updates.

## ADO Comment Update Pattern

> ⚠️ **Do NOT use `reply_to_comment`** — that adds a child comment to the thread, not an in-place update. You MUST use the REST API directly.

```powershell
# 1. Get auth token (ADO resource GUID is well-known)
$token = az account get-access-token `
    --resource "499b84ac-1321-427f-aa17-267ca6975798" `
    --query accessToken -o tsv

# 2. Read existing comment content (to merge into)
$getUri = "https://dev.azure.com/{org}/{project}/_apis/git/repositories/{repoId}/pullRequests/{prId}/threads/{threadId}/comments/1?api-version=7.0"
$existing = Invoke-RestMethod -Uri $getUri `
    -Headers @{ Authorization = "Bearer $token" } `
    -Method Get

# 3. Verify marker — confirm this is the digest comment
#    $existing.content should start with "<!-- ai-agent:pr-orchestrator-digest -->"

# 4. Build updated content — merge new rows into $existing.content
$updatedContent = $existing.content  # manipulate this string

# 5. PATCH the comment in-place
$patchUri = "https://dev.azure.com/{org}/{project}/_apis/git/repositories/{repoId}/pullRequests/{prId}/threads/{threadId}/comments/1?api-version=7.0"
$body = @{ content = $updatedContent } | ConvertTo-Json -Depth 2

Invoke-RestMethod -Uri $patchUri `
    -Headers @{
        Authorization  = "Bearer $token"
        "Content-Type" = "application/json"
    } `
    -Method Patch `
    -Body $body
```

**Key rules:**
- **Comment ID is always `1`** — the root comment in a thread (the one with the digest marker).
- **GET before PATCH** — always read existing content first, then merge. Never reconstruct from scratch (risks overwriting Phase 3/4 content on a Phase 5 update).
- **Verify the marker** `<!-- ai-agent:pr-orchestrator-digest -->` on line 1 of the GET response before patching.

## GitHub Update Pattern

For GitHub PRs, use the GitHub CLI instead:

```bash
# Find existing digest comment
COMMENT_ID=$(gh api repos/{owner}/{repo}/issues/{number}/comments \
    --jq '.[] | select(.body | contains("<!-- ai-agent:pr-orchestrator-digest -->")) | .id')

# Update in-place
echo "{updated_content}" | gh api repos/{owner}/{repo}/issues/comments/$COMMENT_ID \
    -X PATCH --input -
```

## Preserving Existing Content on Update

When updating an existing digest, **preserve the "What Was Fixed" history** from the existing comment. Read the existing digest content, parse its "What Was Fixed" rows, and **append** new rows — do NOT replace them. This ensures the digest is a cumulative record of all fixes across every pipeline run, not just the latest run.

Sections to **append** (preserve existing rows, add new ones):
- 🔧 What Was Fixed — each phase sub-section accumulates rows

Sections to **replace** (always use latest data):
- Risk Level
- 👁️ Needs Your Judgment
- ⏱️ Validation Timeline
- ✅ Mechanically Verified
- 🔍 AI Advisory
