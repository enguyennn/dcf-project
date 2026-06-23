---
goal: Build an interactive browser-based DCF (Discounted Cash Flow) model builder for educational/analytical purposes
version: "1.0"
date_created: 2026-06-23
last_updated: 2026-06-23
owner: t-ethnguyen
tags: [dcf, financial-modeling, react, typescript, vite, tailwind, education, github-pages]
---

# Introduction

Requirements Document for the following initiative: Build a greenfield, browser-based Discounted Cash Flow (DCF) model builder application. The tool accepts financial data via Excel upload or plain-text paste, parses it into a standardized format, detects missing fields, asks follow-up questions, and computes an industry-standard enterprise DCF valuation based on Free Cash Flow to the Firm (FCFF). The application MUST be deployed as a static site on GitHub Pages (frontend-only, no backend), built with React + TypeScript + Vite + Tailwind CSS, using SheetJS/xlsx for client-side Excel parsing and Recharts for data visualization. The tool is strictly educational/analytical — it MUST NOT provide investment advice or guarantee accuracy, and MUST surface all assumptions, sources, formulas, and uncertainty to the user. The project is phased: Phase 1 (MVP) delivers static UI with manual assumptions, full DCF calculation engine, and output tables; subsequent phases add Excel upload, internet research integration, and advanced features (comparables, scenarios, export).

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

**Cross-reference conventions**: Functional requirements use the `FR-` prefix, non-functional requirements use `NFR-`, failure modes use `FM-`, and acceptance criteria use `AC-`. These prefixes enable traceability across sections and into the PRD.

## 1. Terminology

| Term | Definition |
|------|------------|
| DCF | Discounted Cash Flow — a valuation method that estimates the present value of an investment based on its expected future cash flows, discounted at an appropriate rate. |
| FCFF | Free Cash Flow to the Firm — cash flow available to all capital providers (equity + debt) after operating expenses and reinvestment. Calculated as NOPAT + Depreciation & Amortization − Capital Expenditures − Change in Net Working Capital. |
| NOPAT | Net Operating Profit After Tax — operating income × (1 − tax rate). Represents earnings available to all capital providers before financing costs. |
| WACC | Weighted Average Cost of Capital — the blended required return of equity and debt holders, weighted by their proportion in the capital structure. Formula: WACC = (E/V) × Re + (D/V) × Rd × (1 − T). |
| Terminal Value (TV) | The estimated value of a business beyond the explicit forecast period, representing the bulk of enterprise value in most DCF models. Computed via perpetuity growth method or exit multiple method. |
| Perpetuity Growth Method | Terminal value calculation assuming cash flows grow at a constant rate forever. Formula: TV = FCFF_n × (1 + g) / (WACC − g), where g is the perpetuity growth rate. |
| Exit Multiple Method | Terminal value calculation applying a valuation multiple (e.g., EV/EBITDA) to the final-year metric. Formula: TV = EBITDA_n × Exit Multiple. |
| Beta (β) | A measure of a stock's systematic risk relative to the market. Used in CAPM to compute cost of equity. |
| ERP | Equity Risk Premium — the excess return investors demand for holding equities over the risk-free rate. |
| CAPM | Capital Asset Pricing Model — formula for cost of equity: Re = Rf + β × ERP, where Rf is the risk-free rate. |
| Cost of Equity (Re) | The return required by equity investors. Computed via CAPM: Re = Risk-Free Rate + β × ERP. |
| Cost of Debt (Rd) | The effective interest rate a company pays on its debt obligations. |
| Enterprise Value (EV) | The total value of a firm's operations — present value of projected FCFFs plus the present value of terminal value. |
| Equity Value | Enterprise Value minus Net Debt. Represents the value attributable to equity holders. |
| Implied Share Price | Equity Value divided by diluted shares outstanding. |
| Net Debt | Total interest-bearing debt minus cash and cash equivalents. |
| Sensitivity Analysis | A technique that tests how the DCF output (e.g., implied share price) changes as key input assumptions (e.g., WACC, growth rate) are varied systematically. |
| Projection Period | The explicit forecast horizon (number of years) over which annual FCFFs are individually estimated before applying a terminal value. |
| Capital Expenditure (CapEx) | Funds used to acquire, upgrade, or maintain physical assets (property, plant, equipment). |
| Net Working Capital (NWC) | Current assets minus current liabilities; changes in NWC affect free cash flow. |
| Diluted Shares Outstanding | Total shares that would be outstanding if all convertible securities (options, warrants, convertible bonds) were exercised. |
| SheetJS/xlsx | A JavaScript library for parsing and writing spreadsheet files (Excel, CSV) entirely in the browser without a server. |
| Recharts | A React-based charting library for building data visualizations. |
| GitHub Pages | A static site hosting service from GitHub that serves files directly from a repository — no server-side execution. |

## 2. Scope

### In Scope

**Phase 1 — MVP (Primary Delivery)**

- Static single-page application deployed on GitHub Pages
- Manual entry of all financial assumptions via form UI (no Excel upload required for MVP)
- Plain-text paste of financial data with parsing to standardized format
- Complete FCFF-based enterprise DCF calculation engine (pure functions)
- WACC computation via CAPM
- Both terminal value methods (perpetuity growth + exit multiple) with user toggle
- 5-year default projection period with user-adjustable length
- Conservative / Base / Optimistic scenario support
- DCF output table displaying year-by-year projections and summary valuation
- Sensitivity analysis table (WACC vs. growth rate matrix)
- Validation warnings for unrealistic inputs
- Educational disclaimer prominently displayed
- Transparency: all formulas, assumptions, and calculations visible to user

**Phase 2 — Excel Upload (Deferred to post-MVP)**

- Excel/CSV file upload with client-side parsing via SheetJS/xlsx
- Automatic field mapping from uploaded data to standardized input schema
- Missing-field detection with follow-up question prompts

**Phase 3 — Internet Research Integration (Deferred to post-MVP)**

- Integration with financial data APIs for auto-populating market data (beta, risk-free rate, ERP)
- Mandatory source citations for all researched data
- Manual-paste fallback when offline or API unavailable

**Phase 4 — Advanced Features (Deferred to post-MVP)**

- Comparable company analysis
- Advanced scenario modeling with probability weighting
- CSV/spreadsheet export of results
- Recharts-based data visualization (waterfall, sensitivity heatmap)
- Inferred-assumption labeling with reasoning explanations

### Out of Scope (deferred)

- Backend server or API — GitHub Pages is static-only; all computation MUST be client-side
- User authentication or data persistence (beyond browser localStorage)
- Real-time market data feeds — requires server-side API keys; deferred to Phase 3+
- Multi-currency support — MVP assumes USD only
- Mobile-native application — responsive web is in scope, native apps are not
- Financial data for banks, insurance companies, or real-estate firms — these require specialized models (no FCFF); the tool MUST warn users but will not implement sector-specific models
- Automated PDF report generation
- Multi-language (i18n) support

## 3. Functional Requirements

- **FR-001**: Plain-Text Financial Data Input
    - **Description**: The application MUST provide a text input area where users can paste raw financial data (e.g., copied from a website or document). The system MUST parse the pasted text to extract revenue, operating income, depreciation & amortization, capital expenditures, change in net working capital, and tax rate.
    - **Acceptance Criteria**:
        - A multi-line text area accepts pasted content
        - The parser extracts numeric values and maps them to the standardized financial field schema
        - Unrecognized or unparseable content triggers a clear error message identifying the problematic lines
        - Successfully parsed data populates the assumptions editor
    - **Priority**: High
    - **Dependencies**: FR-005

- **FR-002**: Manual Assumptions Entry
    - **Description**: The application MUST provide a structured form allowing users to manually enter or override all financial assumptions required for the DCF calculation: revenue, revenue growth rate, operating margin, tax rate, depreciation & amortization, capital expenditures, change in net working capital, risk-free rate, beta, equity risk premium, cost of debt, debt-to-equity ratio, perpetuity growth rate, exit multiple, and diluted shares outstanding.
    - **Acceptance Criteria**:
        - Each input field has a descriptive label and tooltip explaining its meaning
        - Numeric inputs enforce valid ranges and display immediate inline validation
        - Default placeholder values are provided for educational guidance (e.g., risk-free rate ~4%, ERP ~5-6%)
        - Users can switch between percentage and absolute value entry where applicable
    - **Priority**: High
    - **Dependencies**: None

- **FR-003**: FCFF-Based Enterprise DCF Calculation Engine
    - **Description**: The application MUST implement a pure-function calculation engine that computes the full DCF valuation using the following formulas:
        - NOPAT = Operating Income × (1 − Tax Rate)
        - FCFF = NOPAT + D&A − CapEx − ΔNWC
        - Cost of Equity (Re) = Risk-Free Rate + β × ERP
        - WACC = (E/V) × Re + (D/V) × Rd × (1 − Tax Rate)
        - Present Value of each projected FCFF: PV = FCFF_t / (1 + WACC)^t
        - Enterprise Value = Σ PV(FCFF_t) + PV(Terminal Value)
        - Equity Value = Enterprise Value − Net Debt
        - Implied Share Price = Equity Value / Diluted Shares Outstanding
    - **Acceptance Criteria**:
        - All formulas produce mathematically correct results verified against hand-calculated test cases
        - The engine is implemented as pure functions with no side effects (deterministic given inputs)
        - Each intermediate value (NOPAT, FCFF per year, WACC, PV per year, TV, EV, Equity Value) is individually accessible and displayed
        - Edge case: when WACC ≤ perpetuity growth rate, the engine MUST NOT compute terminal value via perpetuity method and MUST display a validation error
    - **Priority**: High
    - **Dependencies**: FR-002

- **FR-004**: Terminal Value Methods with Toggle
    - **Description**: The application MUST support two terminal value calculation methods and provide a UI toggle for the user to switch between them:
        - **Perpetuity Growth Method**: TV = FCFF_n × (1 + g) / (WACC − g)
        - **Exit Multiple Method**: TV = EBITDA_n × Exit Multiple
    - **Acceptance Criteria**:
        - A clearly labeled toggle or radio button switches between the two methods
        - Switching methods immediately recalculates all downstream values (EV, Equity Value, Implied Share Price)
        - When perpetuity growth is selected, the growth rate input is required and validated (g < WACC)
        - When exit multiple is selected, the multiple input is required and validated (> 0)
        - Both methods display the resulting terminal value and its percentage of total enterprise value
    - **Priority**: High
    - **Dependencies**: FR-003

- **FR-005**: Standardized Financial Data Schema
    - **Description**: The application MUST define and enforce a standardized internal schema for financial data. All input methods (text paste, manual entry, future Excel upload) MUST normalize data to this schema before calculation.
    - **Acceptance Criteria**:
        - Schema includes: revenue, operating_income, tax_rate, depreciation_amortization, capital_expenditures, change_in_nwc, net_debt, shares_outstanding (all numeric)
        - Schema includes WACC inputs: risk_free_rate, beta, equity_risk_premium, cost_of_debt, debt_to_equity_ratio
        - Schema includes TV inputs: perpetuity_growth_rate, exit_multiple, final_year_ebitda
        - Schema validation rejects incomplete data with specific field-level error messages
        - Historical data supports multiple years (array of annual records)
    - **Priority**: High
    - **Dependencies**: None

- **FR-006**: Projection Logic
    - **Description**: The application MUST project future financials over a configurable forecast period (default 5 years). Projections MUST be derived from the user's growth assumptions applied to the base-year financials.
    - **Acceptance Criteria**:
        - Users can set the projection period from 1 to 10 years
        - Revenue is projected using the user-specified growth rate(s) — either a single constant rate or year-by-year rates
        - Operating income is derived from projected revenue × operating margin
        - D&A, CapEx, and ΔNWC are projected as percentages of revenue (user-configurable)
        - Each projected year's FCFF is computed and displayed in the output table
    - **Priority**: High
    - **Dependencies**: FR-003, FR-005

- **FR-007**: Conservative / Base / Optimistic Scenarios
    - **Description**: The application MUST support three scenario configurations that adjust key assumptions simultaneously. Users MUST be able to toggle between scenarios and see the valuation update.
    - **Acceptance Criteria**:
        - Three pre-defined scenario profiles exist: Conservative (lower growth, higher WACC), Base (user defaults), Optimistic (higher growth, lower WACC)
        - Users can customize the assumptions within each scenario independently
        - A scenario selector (tabs or dropdown) switches the active scenario
        - All output tables and metrics update reactively when the scenario changes
        - A comparison view shows all three scenarios side-by-side (implied share price, EV, key assumptions)
    - **Priority**: Medium
    - **Dependencies**: FR-003, FR-006

- **FR-008**: DCF Output Table
    - **Description**: The application MUST display a comprehensive output table showing the year-by-year DCF calculation and summary valuation metrics.
    - **Acceptance Criteria**:
        - Table columns include: Year, Revenue, Operating Income, NOPAT, D&A, CapEx, ΔNWC, FCFF, Discount Factor, PV of FCFF
        - A summary section below the table shows: Terminal Value, PV of Terminal Value, Enterprise Value, Net Debt, Equity Value, Diluted Shares, Implied Share Price
        - Terminal Value as % of Enterprise Value is prominently displayed
        - All numbers are formatted with appropriate decimal places and thousand separators
    - **Priority**: High
    - **Dependencies**: FR-003, FR-006

- **FR-009**: Sensitivity Analysis Table
    - **Description**: The application MUST generate a two-dimensional sensitivity table showing how the implied share price varies across a range of WACC values and perpetuity growth rates (or exit multiples).
    - **Acceptance Criteria**:
        - Default matrix: 5 WACC values (±1% from base in 0.5% steps) × 5 growth rate values (±1% from base in 0.5% steps)
        - Users can adjust the range and step size
        - The cell corresponding to the base-case assumptions is visually highlighted
        - Color coding (green/yellow/red gradient) indicates relative valuation levels
    - **Priority**: High
    - **Dependencies**: FR-003, FR-004

- **FR-010**: Validation Warnings
    - **Description**: The application MUST detect and surface warnings for potentially unrealistic or problematic inputs. Warnings MUST NOT block calculation but MUST be clearly visible.
    - **Acceptance Criteria**:
        - Warning: WACC ≤ perpetuity growth rate (perpetuity TV method is mathematically invalid)
        - Warning: Revenue growth rate > 30% or < −20% (extreme growth assumption)
        - Warning: Operating margin > 50% or < −10% (unrealistic margin)
        - Warning: CapEx or ΔNWC is zero or negative when revenue is growing (likely missing data)
        - Warning: Terminal Value > 85% of Enterprise Value (model heavily reliant on TV)
        - Warning: Required fields are missing or zero
        - Warning: Industry is banking, insurance, or real estate (FCFF model may be inappropriate)
        - Each warning includes an educational explanation of why it matters
        - Warnings are displayed in a dedicated panel adjacent to the relevant input or output
    - **Priority**: High
    - **Dependencies**: FR-003, FR-005

- **FR-011**: Landing Page
    - **Description**: The application MUST present a landing page that introduces the tool, explains its educational purpose, and provides clear entry points for the two input methods (manual entry and text paste).
    - **Acceptance Criteria**:
        - Page displays the tool name, a brief description of DCF valuation, and the educational disclaimer
        - Two clear call-to-action buttons: "Enter Assumptions Manually" and "Paste Financial Data"
        - A brief explanation of what data the user will need
    - **Priority**: High
    - **Dependencies**: None

- **FR-012**: Assumptions Editor Panel
    - **Description**: The application MUST provide a dedicated panel/section where all current assumptions are listed, editable, and grouped by category (Operating, Growth, WACC Components, Terminal Value).
    - **Acceptance Criteria**:
        - Assumptions are grouped under clear headings: Operating Assumptions, Growth Assumptions, WACC Components, Terminal Value Assumptions
        - Each assumption shows its current value, unit (%, $, x), and an info tooltip
        - Changes to any assumption trigger immediate recalculation of outputs
        - A "Reset to Defaults" button restores educational placeholder values
    - **Priority**: High
    - **Dependencies**: FR-002

- **FR-013**: Educational Disclaimer Display
    - **Description**: The application MUST prominently display an educational disclaimer on every page/view that shows valuation results. The disclaimer MUST state that the tool is for educational and analytical purposes only, does not constitute investment advice, and that results depend entirely on user-provided assumptions.
    - **Acceptance Criteria**:
        - Disclaimer is visible without scrolling on any results view
        - Disclaimer text includes: "For educational and analytical purposes only. Not investment advice. Results are entirely dependent on user-provided assumptions and may not reflect actual company value."
        - Disclaimer cannot be permanently dismissed (it may be minimized but must remain accessible)
        - Disclaimer is visually distinct (e.g., bordered box, warning icon)
    - **Priority**: High
    - **Dependencies**: None

- **FR-014**: Formula Transparency
    - **Description**: The application MUST make all calculation formulas visible and accessible to the user, supporting the educational mission.
    - **Acceptance Criteria**:
        - Each computed metric (NOPAT, FCFF, WACC, PV, TV, EV, Equity Value, Implied Price) has an expandable "Show Formula" control
        - Expanding shows the formula with the actual numeric values substituted in
        - A dedicated "Methodology" page/section explains the full DCF methodology with formulas in mathematical notation
    - **Priority**: Medium
    - **Dependencies**: FR-003

- **FR-015**: Missing Field Detection and Follow-Up Questions
    - **Description**: When parsed or entered data is incomplete (required fields missing), the application MUST identify the missing fields and present targeted follow-up questions to the user.
    - **Acceptance Criteria**:
        - After text paste parsing, the system identifies which required schema fields were not found
        - A follow-up panel lists each missing field with a brief explanation of what it is and why it's needed
        - Users can enter missing values directly in the follow-up panel
        - Once all required fields are populated, calculation proceeds automatically
    - **Priority**: High
    - **Dependencies**: FR-001, FR-005

- **FR-016**: Company Information Input
    - **Description**: The application MUST collect basic company identification information to contextualize the valuation.
    - **Acceptance Criteria**:
        - Fields: Company Name (required), Ticker Symbol (optional), Industry/Sector (optional), Currency (display-only, defaulting to USD)
        - Industry selection triggers relevant warnings (e.g., banking/insurance/real-estate FCFF caveat)
        - Company name appears in output headers and export filenames
    - **Priority**: Medium
    - **Dependencies**: FR-010

## 4. Non-Functional Requirements

- **NFR-001**: Static Deployment Constraint
    - **Metric:** Application MUST deploy and run entirely from GitHub Pages with zero server-side components. Build output MUST be a static bundle (HTML + JS + CSS + assets).
    - **Rationale:** GitHub Pages provides free, reliable hosting with no infrastructure management. This constraint ensures the tool remains accessible to beginners and has zero operational cost.
    - **Testing Approach:** Verify production build produces only static assets; deploy to GitHub Pages and confirm all features function without any backend calls.

- **NFR-002**: Client-Side Performance
    - **Metric:** Full DCF recalculation (including sensitivity table generation) MUST complete in < 100ms on a modern browser (Chrome/Firefox/Edge, 2020+ hardware). Initial page load MUST complete in < 3 seconds on a 4G connection.
    - **Rationale:** Instant feedback on assumption changes is critical for the exploratory educational experience.
    - **Testing Approach:** Performance benchmarks using browser Performance API; Lighthouse CI score ≥ 90 for performance.

- **NFR-003**: Browser Compatibility
    - **Metric:** Application MUST function correctly on the latest two major versions of Chrome, Firefox, Edge, and Safari.
    - **Rationale:** Broad accessibility for users across different platforms.
    - **Testing Approach:** Cross-browser manual testing checklist; automated Playwright tests on Chrome and Firefox.

- **NFR-004**: Accessibility
    - **Metric:** Application MUST conform to WCAG 2.1 Level AA. All form inputs MUST have associated labels. All data tables MUST have proper header markup. Color MUST NOT be the sole means of conveying information.
    - **Rationale:** Educational tools must be accessible to all users including those using assistive technologies.
    - **Testing Approach:** Automated axe-core scans; manual keyboard navigation testing; screen reader verification of key flows.

- **NFR-005**: Testability of Calculation Engine
    - **Metric:** All pure calculation functions MUST have ≥ 95% unit test coverage. Each formula MUST be verified against at least 3 hand-calculated test cases including edge cases.
    - **Rationale:** Financial calculations must be provably correct; the pure-function architecture enables exhaustive testing without UI dependencies.
    - **Testing Approach:** Vitest unit tests with coverage reporting; test cases derived from textbook DCF examples with known correct answers.

- **NFR-006**: Educational Transparency
    - **Metric:** Every computed value displayed to the user MUST be traceable to its formula and input assumptions within 1 click/interaction. No "black box" calculations.
    - **Rationale:** The tool's primary purpose is education; users must understand how results are derived.
    - **Testing Approach:** Manual UX review confirming every output has a visible formula path; automated check that all computed fields have associated formula metadata.

- **NFR-007**: No Investment Advice
    - **Metric:** The application MUST NOT use language that could be construed as investment recommendations (e.g., "buy", "sell", "undervalued", "overvalued"). Results MUST always be qualified with "based on your assumptions" or equivalent.
    - **Rationale:** Legal and ethical obligation to prevent misuse of educational tools as financial advice.
    - **Testing Approach:** Content audit of all UI text; grep for prohibited terms in codebase; user testing to confirm messaging clarity.

- **NFR-008**: Bundle Size
    - **Metric:** Production JavaScript bundle MUST be < 500KB gzipped (including SheetJS and Recharts when added in later phases). Phase 1 (no SheetJS/Recharts) SHOULD be < 200KB gzipped.
    - **Rationale:** Fast loading on constrained connections; GitHub Pages has no CDN optimization beyond what the browser provides.
    - **Testing Approach:** Build output size check in CI; bundle analyzer for dependency auditing.

- **NFR-009**: Code Maintainability
    - **Metric:** TypeScript strict mode MUST be enabled. No `any` types in calculation engine modules. ESLint with recommended rules MUST pass with zero errors.
    - **Rationale:** Type safety prevents subtle numeric errors in financial calculations; maintainability supports the educational/learning context of the project.
    - **Testing Approach:** `tsc --noEmit` in CI; ESLint checks; PR review for type safety in calc modules.

- **NFR-010**: Responsive Design
    - **Metric:** Application MUST be usable on viewport widths from 768px (tablet) to 2560px (ultrawide). Tables MUST be horizontally scrollable on smaller viewports rather than truncated.
    - **Rationale:** Users may work on laptops, desktops, or tablets.
    - **Testing Approach:** Visual regression tests at 768px, 1280px, and 1920px breakpoints.

## 5. Failure Modes and Recovery

| ID | Failure | Detection | Recovery |
|----|---------|-----------|----------|
| FM-001 | Malformed Excel/CSV file uploaded (Phase 2+) | SheetJS throws parse error or returns empty/corrupted data | Display user-friendly error: "Unable to read file. Please ensure it is a valid .xlsx or .csv file." Offer manual entry as fallback. |
| FM-002 | Unmappable rows in pasted text | Parser cannot map lines to any recognized financial field | Highlight unrecognized lines in the text area; display: "Could not interpret the highlighted lines. Please enter these values manually." Partial successful parses are kept. |
| FM-003 | Missing required fields after input | Schema validation detects null/undefined required fields | Trigger follow-up question panel (FR-015) listing missing fields with explanations. Block calculation until resolved. |
| FM-004 | WACC ≤ perpetuity growth rate (divide-by-zero / negative TV) | Pre-calculation validation check: if (WACC <= g) | Display prominent error on TV section: "Perpetuity growth rate must be less than WACC. Terminal value cannot be calculated." Suggest switching to exit multiple method. Do not display nonsensical negative values. |
| FM-005 | No internet access (Phase 3+ research feature) | Fetch/API call timeout or network error | Display: "Unable to reach data source. You can enter values manually." Enable manual-paste input for market data fields. Cache last-known values in localStorage if available. |
| FM-006 | Invalid numeric inputs (NaN, negative where positive required, non-numeric characters) | Input validation on change/blur; type coercion check | Inline field-level error message: "Please enter a valid number." Prevent field from being used in calculation until corrected. Preserve other valid inputs. |
| FM-007 | Export failure (Phase 4+ CSV/spreadsheet export) | File system API error or blob generation failure | Display: "Export failed. Please try again or copy the data from the table directly." Provide copy-to-clipboard fallback for table data. |
| FM-008 | Browser out of memory on large sensitivity matrix | Performance.memory API (Chrome) or computation timeout > 5 seconds | Limit sensitivity matrix size; display: "Matrix too large for browser. Reducing to default 5×5 grid." Auto-reduce dimensions. |
| FM-009 | LocalStorage quota exceeded | try/catch on localStorage.setItem | Display: "Unable to save preferences. Browser storage is full." Application continues functioning without persistence. |

## 6. Assumptions and Interpretations

### Assumptions

| ID | Assumption | Confidence | Impact if Wrong | Traces To |
|----|-----------|------------|-----------------|-----------|
| ASM-001 | The default projection period is 5 years, which is standard for most DCF models. Users can adjust from 1–10 years. | High | Minor — users simply adjust the slider. Calculation logic already supports variable periods. | FR-006 |
| ASM-002 | The application is frontend-only for the MVP (Phases 1–2). No backend, no server-side API calls, no database. All state is ephemeral or in localStorage. | High | Major — would require re-architecture with server infrastructure, hosting changes, and deployment pipeline rework. | NFR-001, FR-003 |
| ASM-003 | Manual research paste is the default/only method for market data (beta, risk-free rate, ERP) in MVP. Automated internet research requiring API keys is deferred to Phase 3+. | High | Moderate — users must source their own market data. UX is slightly less streamlined but avoids API key/server dependency. | FR-002, NFR-001 |
| ASM-004 | All monetary values are in USD. Multi-currency conversion is out of scope. | High | Low for MVP — most educational DCF examples use USD. Would require exchange rate data source and conversion logic if wrong. | FR-005 |
| ASM-005 | Implied share price uses diluted shares outstanding (not basic) for conservatism. | High | Low — produces slightly lower per-share value, which is standard practice. If basic shares are needed, it's a simple input swap. | FR-003 |
| ASM-006 | The FCFF approach (not FCFE) is appropriate for the general-purpose DCF model. FCFE would require modeling debt repayments and is more specialized. | High | Moderate — FCFE users would need a different tool. Adding FCFE would be a separate feature. | FR-003 |
| ASM-007 | D&A, CapEx, and ΔNWC are projected as percentages of revenue for simplicity. Users can override individual year values. | Medium | Moderate — some companies have lumpy CapEx patterns. Percentage-of-revenue is a common simplification for educational models. | FR-006 |
| ASM-008 | The tech stack is React 18+ with TypeScript, Vite as build tool, Tailwind CSS for styling, and Vitest for testing. These are fixed constraints, not choices to be evaluated. | High | Major — changing the tech stack would invalidate all implementation planning. | NFR-001, NFR-009 |
| ASM-009 | SheetJS/xlsx is added in Phase 2 (not Phase 1 MVP). Phase 1 supports only text paste and manual entry. | Medium | Low — adding SheetJS to Phase 1 increases bundle size and scope but is technically straightforward. | FR-001, NFR-008 |
| ASM-010 | Recharts is added in Phase 4 (not Phase 1 MVP). Phase 1 displays data in tables only. | Medium | Low — adding Recharts to Phase 1 increases scope but is technically straightforward. Charts are enhancement, not core. | NFR-008 |
| ASM-011 | The tool targets users who already have financial data available (from annual reports, SEC filings, or financial websites). It does not teach users how to find or read financial statements. | Medium | Moderate — if targeting complete beginners to finance, additional educational content about reading financial statements would be needed. | FR-011, FR-002 |
| ASM-012 | The target user for building the application is a beginner learning React/TypeScript/GitHub, but the END USER of the built tool has basic financial literacy (understands revenue, operating income, etc.). | Medium | Low — affects tooltip/explanation depth but not calculation logic. | FR-002, FR-014 |
| ASM-013 | localStorage is available in the target browsers for saving user preferences and last-used assumptions. No fallback to cookies or IndexedDB is needed. | High | Low — graceful degradation already specified in FM-009. | FM-009 |

### Alternative Interpretations

| ID | Ambiguity | Chosen Interpretation | Alternatives Considered | Rationale |
|----|-----------|----------------------|------------------------|-----------|
| ALT-001 | Should the DCF use FCFF (Free Cash Flow to Firm) or FCFE (Free Cash Flow to Equity)? | FCFF — enterprise DCF discounted at WACC | FCFE discounted at cost of equity; Dividend Discount Model | FCFF is the most widely taught and general-purpose DCF approach. It does not require modeling debt schedules and works for companies regardless of dividend policy. Most textbooks and analyst training programs use FCFF. |
| ALT-002 | Which terminal value method should be the default? | Perpetuity Growth Method as default (with exit multiple as toggle option) | Exit multiple as default; show both simultaneously; force user to choose | Perpetuity growth is more theoretically grounded and self-contained (no need for comparable multiples). It's the standard pedagogical choice. Exit multiple is provided as an alternative for users who prefer it. |
| ALT-003 | How should internet research integration work given the GitHub Pages static constraint? | Defer to Phase 3; MVP uses manual input only. Phase 3 may use a client-side approach (e.g., user provides their own API key) or a lightweight proxy. | Build a backend from the start; use a free API with no key; scrape financial websites client-side | A static site cannot securely store API keys. Client-side API calls with user-provided keys are possible but complex for MVP. Manual entry is simpler, more reliable, and sufficient for Phase 1 educational purposes. |
| ALT-004 | What level of Excel schema flexibility should be supported (Phase 2)? | Flexible column-name matching with fuzzy/alias mapping (e.g., "Rev", "Revenue", "Total Revenue" all map to revenue) | Strict template: users must use exact column names; fully automatic: ML-based column inference | Fuzzy matching with a known alias dictionary provides good UX without requiring ML. Users of different financial data sources use different column headers. A strict template would frustrate users. |
| ALT-005 | Should the sensitivity analysis vary WACC + growth rate, or should users choose which two variables to cross? | Fixed: WACC × Growth Rate for MVP; user-selectable axes deferred | User picks any two variables; multiple sensitivity tables for different pairs | WACC and growth rate are the two most impactful and commonly sensitized variables in DCF. A fixed matrix reduces UI complexity for MVP while covering the most common use case. |
| ALT-006 | Should Phase 1 include charts/visualizations or tables only? | Tables only for Phase 1; Recharts visualizations deferred to Phase 4 | Include basic charts in Phase 1; include sparklines inline in tables | Tables are sufficient for Phase 1 functionality and keep the bundle small. Charts add significant scope (component design, responsive behavior, accessibility) better addressed when the core is stable. |
| ALT-007 | How should "scenarios" work — preset deltas from base, or fully independent assumption sets? | Fully independent assumption sets initialized from base with ±adjustments | Fixed percentage deltas (e.g., ±20% on growth); hybrid with some locked and some free fields | Independent sets give users maximum flexibility and better represent how analysts actually use scenarios. Preset deltas are too rigid for educational exploration. |

## 7. Acceptance Criteria

| ID | Criterion | Verification | Traces To |
|----|-----------|--------------|-----------|
| AC-001 | User can paste multi-line financial text and see it parsed into the standardized schema with field labels | Manual test + automated parsing unit tests | FR-001, FR-005 |
| AC-002 | User can manually enter all DCF assumptions via form inputs with inline validation | Manual test + Playwright E2E test | FR-002 |
| AC-003 | Given a complete set of valid inputs, the engine computes NOPAT, FCFF, WACC, PV, TV, EV, Equity Value, and Implied Share Price correctly (verified against 3+ hand-calculated cases) | Vitest unit tests with known-answer test vectors | FR-003, NFR-005 |
| AC-004 | User can toggle between perpetuity growth and exit multiple TV methods and see immediate recalculation | Manual test + Playwright E2E test | FR-004 |
| AC-005 | Application enforces the standardized financial data schema and rejects incomplete data with specific error messages | Unit tests on validation logic | FR-005 |
| AC-006 | Projection table shows year-by-year financials for the configured forecast period (default 5 years, adjustable 1–10) | Manual test + unit tests on projection functions | FR-006 |
| AC-007 | User can switch between Conservative/Base/Optimistic scenarios and see all outputs update | Playwright E2E test | FR-007 |
| AC-008 | DCF output table displays all required columns (Revenue through PV of FCFF) plus summary valuation metrics | Manual visual inspection + snapshot test | FR-008 |
| AC-009 | Sensitivity table renders a WACC × Growth Rate matrix with the base case highlighted and color-coded | Manual test + snapshot test | FR-009 |
| AC-010 | When WACC ≤ growth rate, a prominent error is displayed and perpetuity TV is not calculated | Unit test + E2E test with invalid inputs | FR-010, FM-004 |
| AC-011 | Validation warnings appear for extreme growth (>30%), unrealistic margins (>50%), missing CapEx, TV >85% of EV, and banking/insurance/real-estate industry selection | Unit tests per warning rule | FR-010 |
| AC-012 | Landing page displays tool description, educational disclaimer, and two entry-point buttons | Manual visual test + Playwright | FR-011 |
| AC-013 | Assumptions editor groups inputs by category with tooltips and reset-to-defaults functionality | Manual test + E2E test | FR-012 |
| AC-014 | Educational disclaimer is visible on all results views and cannot be permanently dismissed | Manual test across all views | FR-013, NFR-007 |
| AC-015 | Each computed value has an expandable "Show Formula" with actual numbers substituted | Manual test + E2E test | FR-014, NFR-006 |
| AC-016 | After text paste with missing fields, follow-up panel lists the missing fields and accepts user input | Manual test + E2E test | FR-015 |
| AC-017 | Application deploys to GitHub Pages and all features work without any backend calls | Deploy to GH Pages + manual smoke test | NFR-001 |
| AC-018 | Full DCF recalculation completes in < 100ms; page loads in < 3s on 4G | Lighthouse CI + Performance API benchmarks | NFR-002 |
| AC-019 | Application passes axe-core automated accessibility scan with zero critical violations | axe-core CI integration | NFR-004 |
| AC-020 | Calculation engine has ≥ 95% unit test coverage | Vitest coverage report | NFR-005 |
| AC-021 | Application renders correctly at 768px, 1280px, and 1920px viewport widths | Visual regression tests | NFR-010 |
| AC-022 | Malformed text input shows specific error for unrecognized lines without crashing | Unit test + E2E test | FM-002 |
| AC-023 | Missing required fields trigger follow-up panel and block calculation until resolved | E2E test | FM-003 |
| AC-024 | Invalid numeric inputs show inline error and do not corrupt calculation state | Unit test on validation + E2E test | FM-006 |
| AC-025 | Company info fields accept name, optional ticker/industry, and industry selection triggers appropriate warnings | Manual test + E2E test | FR-016, FR-010 |
