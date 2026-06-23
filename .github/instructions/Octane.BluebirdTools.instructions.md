---
description: 'Bluebird Engineering Copilot MCP tool reference — indexed code search for all documentation agents.'
applyTo: '**/artifacts/scenarios/eng-docs/**/*.md'
---

# Bluebird MCP — Code Search

Use the `code-search` MCP server for indexed code discovery. Faster and more precise than grep for API-level searches. Fall back to workspace search tools when unavailable.

## Key Commands

- **Search code:** `bluebird-engineering_copilot_dynamic_tool_invoker` with `toolName: "search_file_content"` — supports prefixes like `class:`, `interface:`, `method:`, `def:`, `reference:`
- **Find files:** `search_file_paths` for path-based lookups
- **Read code:** `get_file_content` or `get_file_chunk` for file retrieval

Use `base_path` (relative to repo root, starts with `/`) to scope searches.
