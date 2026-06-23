# Accessibility Testing

Run comprehensive automated accessibility audits on web pages using the Playwright MCP server. Test for WCAG compliance and other accessibility barriers across 11 different testing methodologies.

## When to Use

- Validating WCAG 2.0/2.1/2.2 compliance (Level A, AA, AAA)
- Pre-deployment accessibility audits before releasing features
- Testing specific accessibility criteria (headings, links, images, contrast, keyboard navigation, etc.)
- Generating accessibility reports

## Prerequisites

- **MCP Server**: Playwright MCP server (registered as `playwright` in [`artifacts/shared/mcp.json`](../../shared/mcp.json) for the VS Code extension; declared inline in this scenario's [`.mcp.json`](./.mcp.json) for the Copilot CLI plugin)
- **URL**: Valid web page URL accessible from your machine

## Workflows

### Run Accessibility Tests

Execute one or more accessibility tests on a target URL.

**Skill:** [`octane-a11ytester-run`](./skills/octane-a11ytester-run/SKILL.md) — owns input collection, per-test sequencing, browser reset between tests, brief + comprehensive reporting, and save/rerun gates.

**Agent:** [`Octane.A11yTester`](./agents/Octane.A11yTester.agent.md) — carries the declared model, tool allow-list, and step-compliance guarantees.

**Steps:**

1. Invoke the skill from Copilot Chat (VS Code) or the CLI (e.g., `/octane-a11ytester-run`).
2. Provide the **URL** of the web page to test.
3. Optionally provide a **CSS selector** (`Target`) to test a specific element or iframe (e.g., `#main-content`).
4. Select one or more **test types** (`TestTypes`) from the Test Types Reference below.
5. `Octane.A11yTester` navigates to the URL, executes each test against its reference skill, and generates a report.

**Expected Output:**

A structured accessibility report based on the selected test types, including:

- Violations or failures found
- WCAG success criteria references
- Element selectors for each issue
- Remediation guidance

#### Invocation

```shell
# You'll be asked to provide a URL, an optional target selector, and test selection
/octane-a11ytester-run

# You'll be asked to provide an optional target selector and test selection
/octane-a11ytester-run https://example.com

# You'll be asked to provide test selection
/octane-a11ytester-run https://example.com, entire page

# Run axe-core testing on https://example.com scoped to the #TargetA element
/octane-a11ytester-run https://example.com, id="TargetA", axe-core
```

## Test Types Reference

The canonical Testing Library (with full per-test descriptions, WCAG coverage, and links to each reference-skill methodology) lives in the [`octane-a11ytester-run` skill](./skills/octane-a11ytester-run/SKILL.md#testing-library). Short summary:

| Category | Tests |
|----------|-------|
| Automated WCAG scanning | `axe-core` |
| Keyboard & focus | `keyboard-navigation`, `focus-order`, `bypass-blocks` |
| Content semantics | `link-purpose`, `image-function`, `no-missing-headings`, `heading-levels`, `instructions` |
| Visual & layout | `ui-components-contrast`, `reflow` |

## Custom Agents

### Octane.A11yTester

Accessibility testing specialist that orchestrates browser-based accessibility audits. `Octane.A11yTester` follows strict step-by-step testing protocols defined in skills and generates accurate reports using standardized templates. The agent provides a report on violations found and remediation guidance for those issues.

## Tips and Best Practices

- **Test specific elements** using the CSS selector parameter to focus on components or regions.
- **Test specific iframes** — when a web page contains iframes, use a CSS selector to test the iframe content.
- **Review by severity** — address WCAG Level A violations first, then AA, then AAA.

## Related Scenarios

- [A11y Bug Fixing](../a11y-bug-fixing/README.md)

## Changelog

See [CHANGELOG.md](./CHANGELOG.md) for version history and migration
notes. The `1.x → 2.0` entry documents the prompt → skill migration.
