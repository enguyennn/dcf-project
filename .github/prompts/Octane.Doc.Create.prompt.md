---
description: Generate comprehensive living documentation for existing code
argument-hint: The name of the code to document (e.g., Service.Authentication, UserRepository)
model: Claude Opus 4.6 (copilot)
---

## INPUTS

- `Name` (string, required): The name of the code to document (e.g., "Service.Authentication", "UserRepository", "PaymentGateway")

If you do not have a `Name`, you cannot proceed. Ask the user to specify what they want to document.

## PRIMARY DIRECTIVE

Generate comprehensive **living documentation** for `${input:Name}`. The documentation must:
- Follow the template structure exactly
- Capture architecture, design decisions, and key insights
- Be machine-readable for future AI consumption
- Contain no placeholder content - all sections must have real information or be marked [TODO]
- Include enterprise context (design docs, decision history, ownership) when available via WorkIQ and EngHub

## WORKFLOW STEPS

Present the following steps as **trackable todos** to guide progress:

1. **Locate Source**  
   Use `code-search/*` tools or workspace search to find the source files. Identify:
   - Main entry points and classes
   - Related interfaces and types
   - Configuration files
   - Test files

2. **Gather Engineering Hub Context**  
   Use `enghub/*` tools to search for existing internal documentation:
   - Search eng.ms for architecture docs, TSGs, and runbooks related to `${input:Name}`
   - Fetch full page content for highly relevant results
   - Use `resolve-service` and `get-service-nodes` to discover service tree context (ownership, hierarchy)
   - Look for existing onboarding guides or developer docs that may overlap with or inform the new documentation
   
   This step surfaces engineering knowledge that is already published internally — avoid duplicating content that exists on eng.ms. Instead, link to it and layer additional insights on top.

3. **Gather Enterprise Context**  
   Use `work-iq/*` tools to search for relevant enterprise knowledge:
   - Design reviews and tech specs related to `${input:Name}` (search SharePoint, OneDrive)
   - Architecture decision discussions in Teams threads and email chains
   - Meeting notes where `${input:Name}` design was discussed
   - People who authored or contributed to design documents (ownership discovery)
   
   This step enriches the documentation with "why" context that code alone cannot provide.

4. **Analyze Architecture**  
   Examine the codebase to understand:
   - Purpose and responsibilities
   - Dependencies (internal and external)
   - Data flow and key operations
   - Integration points with other systems

5. **Extract Design Decisions**  
   Combine code patterns, EngHub docs, and enterprise context to identify intentional choices:
   - Why certain libraries or frameworks were chosen (check design docs via WorkIQ)
   - Architectural patterns in use (repository, factory, etc.)
   - Error handling strategies
   - Performance optimizations
   - Trade-offs discussed in meetings or email threads (via WorkIQ and EngHub)

6. **Document API Surface**  
   Identify and document:
   - Public interfaces and contracts
   - Configuration options
   - Extension points

7. **Identify Common Scenarios**  
   Based on code analysis, EngHub TSGs/runbooks, and test files:
   - Primary use cases
   - Error scenarios and handling
   - Edge cases
   - Operational scenarios from TSGs (if found on eng.ms)

8. **Generate Documentation**  
   Create the documentation file following the template at `${config:documentation.template}`:
   - Use pseudo-code instead of actual implementation code
   - Mark unknown sections with [TODO: need team input]
   - Include links to design docs and decision sources discovered via WorkIQ
   - Include links to relevant eng.ms pages (TSGs, runbooks, architecture docs) discovered via EngHub
   - Add an ownership/contacts section if people were discovered
   
   **Diagram Configuration:**
   - If `${config:documentation.include_diagrams}` is `true`, include Mermaid diagrams for complex flows
   - Use `${config:documentation.diagram_syntax}` for diagram fencing:
     - `azure-devops`: Use `::: mermaid` opening and `:::` closing
     - `github`: Use standard ``` ```mermaid ``` code blocks
   - If `include_diagrams` is `false`, use simple text flow diagrams instead:
     ```
     [Entry] → [Stage 1] → [Stage 2] → [Output]
     ```

9. **Offer Interview**  
   After generating documentation, ask:
   > "Documentation generated at `${config:documentation.output_path}/${input:Name}.doc.md`. 
   > Would you like me to interview you for team insights? This captures design rationale, gotchas, and production learnings that can't be found in code or eng.ms."

## CODE GRAPH TOOLS

Use `code-search/*` tools for codebase analysis.

## OUTPUT LOCATION

- File Path: `${config:documentation.output_path}/${input:Name}.doc.md`

## DOCUMENTATION PRINCIPLES

1. **Capture "Why" not just "What"** - Code shows what, docs explain why
2. **Use pseudo-code** - Real code drifts, pseudo-code captures intent
3. **Mark unknowns explicitly** - [TODO] is better than guessing
4. **Prioritize design decisions** - These are hardest to reconstruct later
5. **Include failure modes** - What breaks and how to fix it

## TEMPLATE REFERENCE

Follow the structure defined in: `${config:documentation.template}`

The template contains all required sections, formatting rules, and examples. Read it before generating documentation.
