---
name: octane-a11ytester-run
description: >-
  Run a multi-test accessibility audit on a web page using the Playwright
  MCP server. Collects URL, optional target selector, and one or more
  test types from the Testing Library, then orchestrates per-test
  execution, browser reset between tests, brief and comprehensive
  reporting, and end-of-session save/rerun gates. Use when a developer
  says "run accessibility tests", "audit this page for a11y", "check
  WCAG compliance", or "run axe-core on this URL".
---

# Run Accessibility Tests — A11yTester Session

Orchestrate an end-to-end accessibility test session on a target web page
using the Playwright MCP server. This is the canonical entrypoint for the
`accessibility-testing` scenario.

## When to Use

- The user says "run accessibility tests", "audit this page for a11y",
  "check WCAG compliance", or "run axe-core on this URL"
- The user provides a URL (or asks for help testing a page) and one or
  more accessibility criteria they want validated
- The agent should be `Octane.A11yTester` (see
  [agents/Octane.A11yTester.agent.md](../../agents/Octane.A11yTester.agent.md));
  it carries the declared model, tool allow-list, and step-compliance
  guarantees this skill depends on. If a different agent is active,
  this skill will delegate — see [Agent Delegation](#agent-delegation-mandatory).

## Inputs

| Parameter | Required | Description |
|-----------|----------|-------------|
| `URL` | Yes | The web page URL to test for accessibility. If missing, stop and ask. |
| `Target` | Optional | CSS selector for a specific element to scan (e.g., `#main-content`, `.form-container`). If omitted, scan the entire page. The selector must reference an element on the main page — targeting elements nested within iframes is not supported. |
| `TestTypes` | Yes | One or more accessibility tests to run from the Testing Library (below). If missing, present the library and ask the user to choose. |

If `URL` is missing, stop and ask. Do not provide an example request — just
state that the input is required.

If `TestTypes` is missing, present the Testing Library options and ask the
user to choose one or more.

## Testing Library

Each entry maps to a reference skill in this scenario's `skills/` tree.

| Tag | Test | Coverage | Reference |
|-----|------|----------|-----------|
| `axe-core` | Axe-Core Violations — Automated WCAG compliance scanning using the axe-core engine | WCAG 2.0/2.1/2.2 A/AA/AAA (configurable) | [axe-core-testing](../axe-core-testing/SKILL.md) |
| `keyboard-navigation` | Keyboard Navigation — Tests that all interactive components are reachable via keyboard | WCAG 2.1.1 | [keyboard-navigation-testing](../keyboard-navigation-testing/SKILL.md) |
| `link-purpose` | Link Purpose — Tests that link purpose is described by link text alone or with preceding context | WCAG 2.4.4 | [link-purpose-testing](../link-purpose-testing/SKILL.md) |
| `image-function` | Image Function — Tests that every image is coded as meaningful or decorative | WCAG 1.1.1 | [image-function-testing](../image-function-testing/SKILL.md) |
| `focus-order` | Focus Order — Tests that focus order preserves meaning and operability | WCAG 2.4.3 | [focus-order-testing](../focus-order-testing/SKILL.md) |
| `ui-components-contrast` | UI Components Contrast — Tests that UI component states have sufficient contrast | MAS 1.4.3, WCAG 1.4.11 | [ui-components-contrast-testing](../ui-components-contrast-testing/SKILL.md) |
| `no-missing-headings` | No Missing Headings — Tests that text that looks like a heading is coded as one | WCAG 1.3.1, 2.4.6 | [no-missing-headings-testing](../no-missing-headings-testing/SKILL.md) |
| `heading-levels` | Heading Levels — Tests that a heading's programmatic level matches its visual level | WCAG 1.3.1 | [heading-levels-testing](../heading-levels-testing/SKILL.md) |
| `bypass-blocks` | Bypass Blocks — Tests that the page offers a keyboard-accessible way to skip repetitive content | WCAG 2.4.1 | [bypass-blocks-testing](../bypass-blocks-testing/SKILL.md) |
| `instructions` | Instructions — Tests that native-widget labels and instructions are programmatically determinable | WCAG 1.3.1, 2.5.3 | [instructions-testing](../instructions-testing/SKILL.md) |
| `reflow` | Reflow — Tests that content is visible without scrolling in two dimensions | WCAG 1.4.10 | [reflow-testing](../reflow-testing/SKILL.md) |

Report formatting is owned by [report-templates](../report-templates/SKILL.md).

## Agent Delegation (MANDATORY)

This skill is designed to run under the `Octane.A11yTester` agent (see
[agents/Octane.A11yTester.agent.md](../../agents/Octane.A11yTester.agent.md)),
which carries the model declaration, the `playwright/*` tool allow-list,
and the step-compliance + testing-quality guarantees the per-test
reference skills assume.

**Before executing any step below, check the active agent:**

- **If the active agent IS `Octane.A11yTester`** → proceed to `## Primary
  Directive`.
- **If the active agent is NOT `Octane.A11yTester`** → you MUST delegate
  this skill's execution to `Octane.A11yTester` instead of running it
  yourself. Use the host's agent-switching mechanism:
  - **VS Code Copilot Chat**: instruct the user to re-invoke under the
    target agent (e.g., `@Octane.A11yTester /octane-a11ytester-run …`) and
    stop.
  - **Copilot CLI**: re-invoke with `--agent Octane.A11yTester` (e.g.,
    `copilot --agent Octane.A11yTester -p "/octane-a11ytester-run …"`) or
    launch `Octane.A11yTester` as a sub-agent for this task and pass
    through the inputs.
  - **Any other host / orchestrator** (Conductor, A2A, etc.): dispatch
    to `Octane.A11yTester` as a sub-agent and forward `URL`, `Target`,
    and `TestTypes`.

Do **not** silently execute the workflow under a generic or unrelated
agent — the per-test reference skills assume the `Octane.A11yTester`
tool allow-list and step-compliance contract, and running them
elsewhere may fabricate results or skip required pauses.

## Primary Directive

Execute comprehensive accessibility testing on the provided `URL` using the
Playwright MCP server. Run the selected `TestTypes` by following the
methodology in the corresponding reference skill. Generate an actionable
accessibility report.

## Steps

Present the following steps as **trackable todos** to guide progress.

### 1. Validate Inputs

- Confirm the URL is valid and accessible.
- Confirm at least one test type is selected from the Testing Library.
- If inputs are missing, stop and request them from the user.

### 2. Initialize Browser Session

- Use `mcp_playwright_browser_navigate` to open the `URL`.
- Wait for the page to fully load (network idle).
- Use `mcp_playwright_browser_snapshot` to capture the initial
  accessibility tree.
- Verify the page loaded successfully.

### 3. Scope to Target Element (if `Target` provided)

- If `Target` is provided:
  - Click on the target element to set focus within it.
  - **All subsequent testing MUST be limited to elements WITHIN this
    target only.**
  - Do NOT test elements outside the target selector.
  - Tab sequence testing starts FROM the first focusable element INSIDE
    the target.
  - Widget inventory only counts widgets INSIDE the target.
- If the target is an iframe, click into the iframe first to establish
  focus context.
- If no target is provided, test the entire page.

### 4. Execute Selected Tests

> ⚠️ **QUALITY REQUIREMENT**: Each test must be executed with full
> thoroughness, regardless of how many tests are selected. Do NOT take
> shortcuts when running multiple tests:
>
> - **Simulate real interactions**: If the test requires it, actually
>   press Tab/Arrow/Enter/Escape keys rather than querying DOM
>   attributes.
> - **Test ALL elements**: Test every element necessary, not just a
>   sample.
> - **Document step-by-step**: Record each action and display the result
>   to the user as you test.
> - **Investigate root causes**: When violations are found, determine
>   why (e.g., duplicate DOM elements, missing attributes).

**For EACH selected test in `TestTypes`:**

#### 4a. Reset Browser State (skip for first test)

If this is NOT the first test in the sequence:

- Reset viewport to default size:
  `await page.setViewportSize({ width: 1280, height: 720 });`
- Reload the page: `await page.reload({ waitUntil: 'load' });`
- Wait for dynamic content to load (3 seconds).
- Re-scope to target element if `Target` was provided.

This ensures each test starts with a clean, consistent page state.

#### 4b. Execute the Test

- Follow the methodology in the corresponding reference skill (e.g.,
  if `keyboard-navigation` is selected, follow
  [keyboard-navigation-testing](../keyboard-navigation-testing/SKILL.md)).
- Execute each numbered step in the skill file in order.
- Do not skip or combine steps.
- **If a skill file instructs you to pause and ask the user before
  continuing (e.g., checkpoint confirmations), you MUST follow those
  directions and wait for user input before proceeding.**
- Complete **all steps** in the test thoroughly before proceeding.
- **Ignore how long it takes to run the tests; prioritize quality and
  thoroughness over speed.**

### 5. Display Brief Test Report (MANDATORY)

For each completed test:

- Display a **Brief Test Report** by following the
  [report-templates](../report-templates/SKILL.md) skill.
- If no violations were found, display:
  `✅ No violations found for {Test Name}`.
- This step must be executed before proceeding to the next test or the
  final report.

### 6. Display a Comprehensive Test Report

- Compile a **Comprehensive Test Report** by following the
  [report-templates](../report-templates/SKILL.md) skill.

### 7. Save / Rerun Gates

- After displaying the comprehensive report, ask the user if they would
  like to save the report. If yes, save the report to a file and
  confirm the save was successful.
- Ask the user if they would like to run another test on a different
  URL or with different test types. If yes, loop back to Step 1.

## Example

```text
User: /octane-a11ytester-run https://example.com #main-content axe-core,keyboard-navigation

Agent (Octane.A11yTester):
  - URL: https://example.com ✓
  - Target: #main-content ✓
  - TestTypes: [axe-core, keyboard-navigation] ✓

  [1/4] Navigating to https://example.com ...
  [2/4] Scoped to #main-content
  [3/4] Running axe-core ... (follows axe-core-testing/SKILL.md)
        Brief report: 2 violations (1 serious, 1 moderate)
  [4/4] Resetting browser state, re-scoping, then running
        keyboard-navigation ... (follows keyboard-navigation-testing/SKILL.md)
        Brief report: ✅ No violations found for Keyboard Navigation

  Comprehensive Test Report
  =========================
  URL: https://example.com   Target: #main-content
  Tests: axe-core, keyboard-navigation
  Total violations: 2 (1 serious, 1 moderate)
  ...

  Save this report to a file? (y/n)
  Run another test? (y/n)
```

## Output

A Comprehensive Test Report (structure defined by
[report-templates](../report-templates/SKILL.md)) covering all selected
test types, with cross-referenced findings and prioritized remediation
steps. On user confirmation, the report is written to disk.
