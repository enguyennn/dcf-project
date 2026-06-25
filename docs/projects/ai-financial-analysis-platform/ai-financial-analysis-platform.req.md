---
title: "Transform DCF Platform into AI-Powered Financial Analysis Tool"
type: requirements
status: draft
version: "1.0"
date: 2026-06-25
project: ai-financial-analysis-platform
author: SddPlanner
tags: [ai, dcf, financial-analysis, natural-language, market-research, ux]
prefix_registry:
  FR: Functional Requirement
  NFR: Non-Functional Requirement
  FM: Failure Mode
  AC: Acceptance Criterion
  ASM: Assumption
  ALT: Alternative Interpretation
  US: User Story
  DEP: Dependency
  RSK: Risk
  CON: Constraint
---

# Requirements: Transform DCF Platform into AI-Powered Financial Analysis Tool

## 1. Overview & Purpose

This initiative transforms the existing client-side DCF Model Builder — a static React SPA deployed on Vercel — into an AI-powered financial analysis platform. The platform will accept natural-language descriptions of companies, industries, or business ideas; leverage a server-side LLM to parse intent and extract financial assumptions; auto-retrieve market data without requiring user-supplied API keys; and guide users through a structured multi-step workflow from input to final valuation output.

### 1.1 Current State (Verified)

| Aspect | Current Implementation |
|--------|----------------------|
| Stack | React 18.3.1 + TypeScript 5.6.2 (strict) + Vite 6 + Tailwind 3.4.19 |
| Deployment | 100% client-side static SPA on Vercel; `vercel.json` has SPA rewrites only; NO serverless functions |
| Input Parsing | `src/utils/parsePlainText.ts` — rigid regex `LINE_PATTERN` with fixed `ALIASES` array; unmatched lines pushed to `errors[]` |
| Market Data | `src/utils/researchApi.ts` — `fetchMarketData(ticker, apiKey)` calls Alpha Vantage; user supplies key via `localStorage('dcf.apiKey')` through `SettingsPanel` |
| Navigation | Two-state view: `'landing' | 'workspace'`; no guided multi-step workflow |
| Output Model | `DCFOutputs`: enterpriseValue, equityValue, impliedSharePrice, wacc, projections; NO IRR calculation |
| Bundle | ~58KB gzipped; xlsx + recharts lazy-loaded; constraint <200KB gz |
| Tests | Vitest 4 (node env) in `tests/` directory; full coverage for utils |

### 1.2 Target State

An AI-driven financial analysis platform that:
- Accepts free-form natural language and produces a complete DCF model from a single sentence
- Retrieves market/industry data automatically via server-side integrations (no user API keys)
- Guides users through a clear step-based workflow (input → AI assumptions → review → results)
- Provides transparent, editable AI-generated assumptions with source attribution
- Maintains current bundle performance constraints and Vercel deployment model

## 2. Scope

### 2.1 In-Scope

- Natural language input parsing via server-side LLM integration
- Server-side market data retrieval (proxy/serverless) eliminating user API keys
- Intelligent default assumption generation with industry benchmarks
- Robust error handling replacing rigid regex parsing
- Guided multi-step workflow UI (input → assumptions → validation → output)
- Improved UI hierarchy, navigation, typography, and visual components
- Loading states and responsive feedback during AI/data processing
- Assumption transparency (estimated vs. user-provided labels, source attribution)

### 2.2 Out-of-Scope

- Mobile-native applications (responsive web only)
- Real-time stock trading or portfolio management
- Multi-user collaboration or shared workspaces
- Custom financial model types beyond DCF (e.g., LBO, comparable company analysis as primary output)
- User authentication/accounts (stateless sessions initially)
- Historical analysis storage (nice-to-have, deferred)
- PDF/Excel export (nice-to-have, deferred)
- "Explain my valuation" AI feature (nice-to-have, deferred)
- Scenario analysis with best/worst cases (nice-to-have, deferred)

## 3. User Stories

### US-001: Natural Language Company Description
**As a** non-finance user,
**I want to** describe a company or business idea in plain English (e.g., "A mid-size SaaS company growing 30% YoY with 70% gross margins"),
**So that** the system generates a complete DCF valuation without requiring me to know specific financial inputs.

**Acceptance Criteria:**
- AC-001: System accepts free-form text of 1–2000 characters without format constraints
- AC-002: AI extracts quantifiable financial assumptions (growth rate, margins, revenue scale, industry) from the description
- AC-003: For vague/incomplete input, system infers reasonable values and marks them as "estimated" with confidence levels
- AC-004: Processing completes in ≤8 seconds from submission to assumption display

### US-002: Zero-Configuration Market Data
**As a** user,
**I want** market data (risk-free rate, beta, equity risk premium) populated automatically,
**So that** I don't need to obtain or manage API keys.

**Acceptance Criteria:**
- AC-005: No API key input field or configuration step visible to the user
- AC-006: Market data retrieval succeeds without any user-supplied credentials
- AC-007: Retrieved data displays source attribution and retrieval timestamp
- AC-008: If market data is unavailable, system falls back to reasonable defaults with explanation

### US-003: Guided Step Workflow
**As a** first-time user,
**I want** a clear step-by-step process guiding me from input to results,
**So that** I understand what's happening at each stage and can intervene where needed.

**Acceptance Criteria:**
- AC-009: Workflow presents exactly 4 steps: (1) Input, (2) AI Assumptions, (3) Review/Edit, (4) Results
- AC-010: Each step is visually distinct with progress indication
- AC-011: User can navigate backward to any previous step without losing data
- AC-012: Step transitions include brief explanations of what happens next

### US-004: Assumption Transparency
**As a** finance-literate user,
**I want to** see which assumptions were AI-generated vs. derived from market data vs. manually entered,
**So that** I can evaluate the reliability of the valuation and override specific values.

**Acceptance Criteria:**
- AC-013: Each assumption displays a badge/label indicating its source (AI-inferred, market data, user-provided, default)
- AC-014: AI-inferred assumptions include a one-line rationale (e.g., "Based on SaaS industry median")
- AC-015: User can override any assumption; overridden values are marked as "user-provided"
- AC-016: A summary shows count of assumptions by source type

### US-005: Error-Free Natural Language Handling
**As a** user entering free-form text,
**I want** the system to never show "unrecognized line" errors,
**So that** I'm not confused by cryptic parsing failures.

**Acceptance Criteria:**
- AC-017: No "unrecognized line" or regex-failure error messages displayed to users
- AC-018: If AI cannot extract any financial meaning, system asks clarifying questions instead of failing
- AC-019: Mixed structured (e.g., "Revenue: 50M") and unstructured input in the same text block is handled gracefully
- AC-020: System provides friendly guidance when input is insufficient (not error messages)

### US-006: Responsive Processing Feedback
**As a** user waiting for AI analysis,
**I want** clear visual feedback during processing,
**So that** I know the system is working and approximately how long to wait.

**Acceptance Criteria:**
- AC-021: Loading skeleton/spinner appears within 200ms of submission
- AC-022: Progress indicator shows processing stage (parsing, researching, generating assumptions)
- AC-023: If processing exceeds 10 seconds, display estimated remaining time or explanation
- AC-024: UI remains interactive (non-blocking) during background processing

## 4. Functional Requirements

### FR-001: AI-Powered Natural Language Input
The system SHALL accept natural-language descriptions of companies, industries, or business ideas and extract structured financial assumptions using a server-side LLM.

| Sub-ID | Detail |
|--------|--------|
| FR-001.1 | Accept free-form English text (1–2000 chars) as primary input mechanism |
| FR-001.2 | Parse input via server-side LLM to extract: revenue/growth, margins, industry classification, scale, competitive position |
| FR-001.3 | Map extracted parameters to `DCFInputs` type fields (revenue, revenueGrowthRate, operatingMarginRate, etc.) |
| FR-001.4 | For parameters not extractable from input, infer from industry benchmarks (see FR-003) |
| FR-001.5 | Return structured response with extracted values + confidence scores + rationale per field |
| FR-001.6 | Support follow-up refinement ("Actually the margins are closer to 60%") modifying existing assumptions |

### FR-002: Automated Market Research Integration
The system SHALL automatically retrieve financial and industry data without user-supplied API keys, populating DCF inputs from external data sources.

| Sub-ID | Detail |
|--------|--------|
| FR-002.1 | Retrieve risk-free rate (10Y Treasury yield) from server-side data provider |
| FR-002.2 | Retrieve company beta from financial data API when ticker is identified |
| FR-002.3 | Retrieve equity risk premium from market data source |
| FR-002.4 | Retrieve industry-average margins, growth rates, and multiples for comparable analysis |
| FR-002.5 | All API keys/secrets stored server-side; zero client-side credential exposure |
| FR-002.6 | Support graceful degradation: if external data unavailable, fall back to defaults with source="default" |
| FR-002.7 | Cache frequently-accessed data (treasury yields, industry benchmarks) with configurable TTL |

### FR-003: Intelligent Default Assumptions
The system SHALL generate reasonable default assumptions from industry standards when user input or market data is incomplete.

| Sub-ID | Detail |
|--------|--------|
| FR-003.1 | Maintain industry benchmark dataset covering ≥10 major industries (SaaS, Manufacturing, Retail, Healthcare, Fintech, Energy, Consumer Goods, Real Estate, Telecom, Media) |
| FR-003.2 | Each benchmark includes: median revenue growth, operating margin, D&A rate, capex rate, NWC rate, cost of debt, typical beta range |
| FR-003.3 | Mark every assumption with metadata: `{value, source: 'industry-benchmark'|'ai-inferred'|'market-data'|'user-provided'|'default', confidence: 'high'|'medium'|'low', rationale: string}` |
| FR-003.4 | Transparency: display rationale for each default in the UI assumptions panel |
| FR-003.5 | Extend existing `AssumptionDefaults` type to include source metadata |

### FR-004: Robust Error Handling for Input Parsing
The system SHALL eliminate rigid regex-based parsing errors and gracefully handle all forms of natural-language and mixed-format input.

| Sub-ID | Detail |
|--------|--------|
| FR-004.1 | Replace `parsePlainText.ts` regex-only path as the PRIMARY parser; retain regex as fast-path for clearly structured input (e.g., "Revenue: 50M") |
| FR-004.2 | For input that fails regex fast-path, route to AI parser (FR-001) instead of returning errors |
| FR-004.3 | Handle mixed structured + unstructured text in single input block |
| FR-004.4 | Never surface raw parsing errors to user; translate to actionable guidance or clarifying questions |
| FR-004.5 | If no financial data extractable after AI parsing, trigger `FollowUpQuestions` component with specific asks |

### FR-005: Improved UI/UX
The system SHALL present a clean, modern interface with clear visual hierarchy, consistent spacing, and enhanced data visualization.

| Sub-ID | Detail |
|--------|--------|
| FR-005.1 | Implement consistent typography scale and spacing system via Tailwind |
| FR-005.2 | Add persistent navigation bar with back button and step indicator |
| FR-005.3 | Cash-flow projection chart (bar + line combo) in results view using existing `Charts` component |
| FR-005.4 | Valuation breakdown waterfall chart (revenue → FCFF → TV → EV → equity value) |
| FR-005.5 | Highlight key outputs (enterprise value, equity value, implied share price) with prominent styling |
| FR-005.6 | Responsive layout: mobile-first with breakpoints at sm/md/lg/xl |

### FR-006: Guided Workflow Experience
The system SHALL implement a step-based workflow guiding users through the analysis process.

| Sub-ID | Detail |
|--------|--------|
| FR-006.1 | Replace binary `'landing' | 'workspace'` view state with 4-step workflow state machine |
| FR-006.2 | Step 1 (Input): accept NL text, structured text, or file upload |
| FR-006.3 | Step 2 (AI Assumptions): display AI-generated assumptions with sources, allow batch accept/reject |
| FR-006.4 | Step 3 (Review/Edit): full `AssumptionsForm` with all editable fields, warnings, market data |
| FR-006.5 | Step 4 (Results): `DcfOutputTable`, `SensitivityTable`, `Charts`, export options |
| FR-006.6 | Allow backward navigation to any previous step; preserve all user modifications |
| FR-006.7 | Optional "Express Mode": skip Step 3 review for users who trust AI defaults |

### FR-007: Seamless Backend Integration
The system SHALL abstract data-fetching and AI processing into server-side services, removing all user-supplied API key requirements.

| Sub-ID | Detail |
|--------|--------|
| FR-007.1 | Implement server-side API layer (Vercel Serverless Functions or Edge Functions) |
| FR-007.2 | Endpoint: `POST /api/parse` — accepts NL text, returns structured `DCFInputs` + metadata |
| FR-007.3 | Endpoint: `GET /api/market-data?ticker=X` — returns market data (beta, risk-free rate, ERP) |
| FR-007.4 | Endpoint: `GET /api/industry-benchmarks?industry=X` — returns industry-specific defaults |
| FR-007.5 | All provider API keys (Alpha Vantage, LLM provider) stored as Vercel environment variables |
| FR-007.6 | Remove `SettingsPanel` API key input; remove `localStorage('dcf.apiKey')` dependency |
| FR-007.7 | Client calls server endpoints via `fetch`; no direct third-party API calls from browser |

### FR-008: Performance & Responsiveness
The system SHALL maintain fast response times and provide clear feedback during AI and data retrieval operations.

| Sub-ID | Detail |
|--------|--------|
| FR-008.1 | Initial page load: bundle <200KB gzipped (current ~58KB + new code must stay under budget) |
| FR-008.2 | AI parsing endpoint response: p95 ≤ 5 seconds |
| FR-008.3 | Market data endpoint response: p95 ≤ 3 seconds |
| FR-008.4 | Display loading skeleton within 200ms of any async operation start |
| FR-008.5 | Non-blocking UI: all async operations run without freezing main thread |
| FR-008.6 | Lazy-load AI parsing logic only when NL input mode selected (code-split) |

## 5. Non-Functional Requirements

### NFR-001: Usability
The platform SHALL be usable by non-finance professionals without prior DCF knowledge.

| Sub-ID | Detail |
|--------|--------|
| NFR-001.1 | All financial terms accompanied by tooltip explanations |
| NFR-001.2 | Workflow requires zero external documentation to complete |
| NFR-001.3 | Error messages written in plain English without technical jargon |

### NFR-002: Reliability
The system SHALL produce consistent, reproducible outputs for identical inputs.

| Sub-ID | Detail |
|--------|--------|
| NFR-002.1 | LLM temperature set to 0 (or near-zero) for financial extraction to maximize determinism |
| NFR-002.2 | Identical NL input produces same extracted assumptions ≥90% of the time |
| NFR-002.3 | Server-side endpoints implement retry with exponential backoff (max 3 retries) |
| NFR-002.4 | Graceful degradation: if AI service unavailable, fall back to enhanced regex parser + defaults |

### NFR-003: Transparency
All AI-generated assumptions SHALL be traceable to their source and rationale.

| Sub-ID | Detail |
|--------|--------|
| NFR-003.1 | Every assumption carries: value, source type, confidence level, one-line rationale |
| NFR-003.2 | Market data displays provider name, retrieval timestamp, and data vintage |
| NFR-003.3 | AI extraction displays which part of user input drove each assumption |

### NFR-004: Maintainability
The system architecture SHALL support easy updates to AI models, data providers, and industry benchmarks.

| Sub-ID | Detail |
|--------|--------|
| NFR-004.1 | LLM provider abstracted behind interface; swappable without client changes |
| NFR-004.2 | Market data provider abstracted behind interface; can switch from Alpha Vantage without client changes |
| NFR-004.3 | Industry benchmark data stored as JSON/config, editable without code changes |
| NFR-004.4 | Existing pure calculation utilities (`dcfCalculations.ts`, `assumptionEngine.ts`) remain unchanged |

### NFR-005: Security
The system SHALL protect API keys and prevent unauthorized access to server-side resources.

| Sub-ID | Detail |
|--------|--------|
| NFR-005.1 | No API keys, secrets, or tokens exposed to client-side code |
| NFR-005.2 | Server-side endpoints validate input (length limits, sanitization) |
| NFR-005.3 | Rate limiting on all server-side endpoints (prevent abuse/cost overrun) |
| NFR-005.4 | CORS restricted to production domain(s) |

### NFR-006: Cost Efficiency
Server-side AI and data operations SHALL remain within budget constraints.

| Sub-ID | Detail |
|--------|--------|
| NFR-006.1 | LLM calls optimized: use smallest model capable of financial extraction (e.g., GPT-4o-mini or equivalent) |
| NFR-006.2 | Cache market data responses (TTL ≥ 1 hour for treasury yields, ≥ 24 hours for industry benchmarks) |
| NFR-006.3 | Monitor per-request cost; alert if average cost exceeds $0.05/analysis |

## 6. Failure Modes

| ID | Scenario | Impact | Mitigation |
|----|----------|--------|------------|
| FM-001 | LLM service unavailable or timeout | User cannot get AI-parsed assumptions | Fall back to enhanced regex parser + industry defaults; display notice that AI is temporarily unavailable |
| FM-002 | Market data provider rate-limited or down | Missing beta/risk-free rate/ERP | Use cached values (if available) or hardcoded educational defaults with "stale data" warning |
| FM-003 | LLM hallucinates unrealistic financial values | Incorrect valuation output (e.g., 500% growth rate) | Validation layer checks AI outputs against plausible ranges; flag outliers for user review |
| FM-004 | User input contains zero extractable financial information | System cannot generate any assumptions | Trigger FollowUpQuestions asking specific questions; do NOT show empty/zero assumptions |
| FM-005 | Bundle size exceeds 200KB gzipped after AI client code added | Violates CON-001 performance constraint | Aggressive code-splitting; AI interaction module lazy-loaded; server does heavy lifting |
| FM-006 | Server-side function cold start adds latency | First request slow (>5s) | Vercel Edge Functions (no cold start) preferred over Node.js serverless; pre-warm strategy |
| FM-007 | AI extracts values in wrong units (e.g., percentage as decimal or vice versa) | Incorrect WACC/valuation by orders of magnitude | Explicit unit normalization layer; validate that rates are in decimal form per existing convention |
| FM-008 | Cost overrun from excessive LLM API calls | Unexpected billing | Rate limiting per IP/session; cost monitoring; circuit breaker at monthly budget cap |

## 7. Constraints

| ID | Constraint | Rationale |
|----|-----------|-----------|
| CON-001 | Initial JS bundle MUST remain <200KB gzipped | Performance requirement; current ~58KB provides headroom but AI client code must be lazy-loaded |
| CON-002 | Deployment MUST remain on Vercel | Existing infrastructure; Vercel Serverless/Edge Functions extend without migration |
| CON-003 | Existing pure utility functions (`dcfCalculations.ts`, `assumptionEngine.ts`, `validation.ts`, `exportResults.ts`) MUST NOT be modified | Validated, tested business logic; new features layer on top |
| CON-004 | TypeScript strict mode, no `any` types | Existing codebase standard; maintains type safety |
| CON-005 | All financial rates stored as decimals (not percentages) | Existing convention in `financialTypes.ts` and all calculation utilities |
| CON-006 | React 18.3.1 functional components + hooks only | Existing architectural pattern; no class components |
| CON-007 | Tailwind CSS for styling (no additional CSS frameworks) | Existing styling approach |

## 8. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Single-sentence-to-model | A single descriptive sentence produces a complete DCF with all required fields populated | End-to-end test: NL input → valid `DCFOutputs` with non-zero enterprise/equity value |
| Manual input reduction | ≥70% reduction in fields requiring manual entry vs. current baseline (8 `FinancialData` fields + 9 `WACCInputs`/`ProjectionInputs` fields = 17 manual fields; target ≤5 manual fields) | Count fields filled by AI/market-data vs. user-entered in typical workflow |
| Parse error elimination | Zero "unrecognized line" errors shown to users for any NL input | Automated test suite with 50+ diverse NL inputs; zero `errors[]` exposed to UI |
| UX satisfaction | Positive feedback from ≥80% of test users on workflow clarity | User testing with 5+ non-finance participants; task completion + satisfaction survey |
| Response time | p95 end-to-end (submit NL → see assumptions) ≤ 8 seconds | Performance monitoring on production endpoints |
| Bundle size | <200KB gzipped total initial load | CI check via `vite build` + `gzip --best` measurement |

## 9. Dependencies & Risks

### 9.1 Dependencies

| ID | Dependency | Type | Impact if Unavailable |
|----|-----------|------|----------------------|
| DEP-001 | LLM Provider (OpenAI GPT-4o-mini or equivalent) | External service | Core NL parsing blocked; fall back to regex |
| DEP-002 | Financial Data Provider (Alpha Vantage or alternative) | External service | Market data unavailable; use cached/defaults |
| DEP-003 | Vercel Serverless/Edge Functions | Platform | Cannot deploy server-side logic; entire FR-007 blocked |
| DEP-004 | Industry Benchmark Dataset | Internal data | Cannot auto-generate industry defaults; manual entry required |

### 9.1 Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| RSK-001 | LLM non-determinism produces inconsistent valuations | High | Medium | Temperature=0; validation ranges; deterministic post-processing |
| RSK-002 | Vercel serverless cold starts degrade UX | Medium | Medium | Use Edge Functions; implement streaming responses |
| RSK-003 | LLM cost exceeds budget at scale | Medium | High | Model selection (cheapest capable); caching; rate limits; budget alerts |
| RSK-004 | Alpha Vantage free tier rate limits (5 calls/min) | High | Low | Cache aggressively; consider paid tier or alternative provider |
| RSK-005 | Bundle size creep from AI client utilities | Low | Medium | Strict code-splitting; server-side heavy logic; CI size check |
| RSK-006 | AI hallucinates plausible-but-wrong financial data | Medium | High | Validation bounds; require user review step; confidence scoring |

## 10. Assumptions & Alternative Interpretations

### ASM-001: Vercel Serverless Functions as Backend
**Assumption:** The "backend" referenced in FR-007 will be implemented as Vercel Serverless Functions (Node.js runtime) co-deployed with the existing static SPA, NOT a separate backend service.
**Confidence:** High
**Impact:** Determines deployment architecture, cold-start behavior, and API routing.
**Rationale:** Vercel already hosts the app; serverless functions are the lowest-friction path requiring no infrastructure migration. `vercel.json` can be extended with `/api/*` routes alongside existing SPA rewrites.

### ASM-002: LLM Provider is OpenAI-Compatible
**Assumption:** The AI parsing service will use an OpenAI-compatible API (GPT-4o-mini or equivalent) with structured output / function-calling for reliable JSON extraction.
**Confidence:** Medium
**Impact:** Determines prompt engineering approach, cost model, and reliability characteristics.
**Rationale:** OpenAI function-calling produces structured JSON reliably; GPT-4o-mini balances cost ($0.15/1M input tokens) with financial reasoning capability.

### ASM-003: Incremental Evolution, Not Rewrite
**Assumption:** The existing React SPA, all pure utility functions, test suite, and component library are preserved. New features are additive layers (new components, new serverless functions, new state management) rather than a rewrite.
**Confidence:** High
**Impact:** Reduces risk and preserves validated business logic; new code layers on top of tested calculations.
**Rationale:** `dcfCalculations.ts`, `assumptionEngine.ts`, `validation.ts` are tested and correct. The initiative's scope is UX + AI + backend, not recalculation logic.

### ASM-004: No User Authentication Required Initially
**Assumption:** The platform remains stateless/anonymous. No user accounts, saved sessions, or personalization in initial scope.
**Confidence:** Medium
**Impact:** Simplifies architecture but limits "save & revisit" nice-to-have.
**Rationale:** Adding auth is a separate initiative; current app is stateless. Rate limiting can use IP/session tokens instead.

### ASM-005: NPV Maps to Enterprise Value; IRR Not In Scope
**Assumption:** Stakeholder reference to "NPV" maps to the existing `enterpriseValue` or `equityValue` DCF output. "IRR" is not a standard DCF output and is excluded unless explicitly requested.
**Confidence:** High
**Impact:** No new calculation logic required; existing `DCFOutputs` type suffices for core valuation display.
**Rationale:** The current engine computes enterprise value (sum of discounted FCFFs + TV) which IS the NPV of future cash flows. IRR requires iterative solving and a different framing (project IRR vs. equity IRR) not present in the codebase.

### ASM-006: Market Data Provider Remains Alpha Vantage (Initially)
**Assumption:** The same Alpha Vantage endpoints currently used client-side will be called server-side initially, with the key moved to Vercel environment variables.
**Confidence:** High
**Impact:** Minimal code change for data retrieval logic; same endpoints, just server-proxied. Rate limits (5/min free tier) become a scaling concern.
**Rationale:** Existing `researchApi.ts` logic is proven; moving it server-side is the simplest path.

### ASM-007: Industry Benchmarks are Static/Curated Data
**Assumption:** The industry benchmark dataset (FR-003) is a curated static JSON file maintained by developers, not dynamically sourced from an external API.
**Confidence:** Medium
**Impact:** Requires initial data curation effort; updates are manual but predictable.
**Rationale:** No reliable free API provides comprehensive industry-level financial benchmarks. Curated data ensures quality and avoids another external dependency.

---

### ALT-001: Backend Architecture
**Context:** FR-002 and FR-007 require server-side processing, but the app is currently 100% client-side static.

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A (Recommended)** | Vercel Serverless Functions (`/api/*` routes) | Zero infrastructure migration; co-deployed; native Vercel integration; scales to zero | Cold starts (1-3s); 10s execution limit (default); Node.js only |
| B | Vercel Edge Functions | No cold starts; global edge deployment; faster p95 | Limited runtime (no Node.js fs); size limits; some npm packages incompatible |
| C | Separate backend service (e.g., Express on Railway/Fly.io) | Full control; no execution limits; persistent connections | Separate deployment; CORS complexity; higher ops burden; cost at idle |
| D | Client-side LLM (WebLLM/WASM) | No server needed; privacy | Huge bundle; slow inference; no secret protection; poor quality |

**Recommendation:** Option A (Vercel Serverless) for LLM proxy + market data; consider Edge Functions for simple caching endpoints.

### ALT-002: LLM Strategy
**Context:** FR-001/FR-004 require genuine NL understanding. Current "AI" is regex only.

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A (Recommended)** | Server-side LLM (GPT-4o-mini) with structured output | High accuracy; function-calling for reliable JSON; low cost per call | Server dependency; latency (2-5s); non-determinism; requires API key management |
| B | Enhanced deterministic parser (regex + rule engine) | No server needed; instant; fully deterministic; zero cost | Cannot handle true NL; limited vocabulary; still fails on creative descriptions |
| C | Hybrid: regex fast-path + LLM fallback | Best of both: instant for structured input, AI for NL | Complexity; two code paths; inconsistent UX between paths |

**Recommendation:** Option C (Hybrid) — use regex fast-path for clearly structured input (preserves speed), route everything else to server-side LLM.

### ALT-003: Market Data Without User Keys
**Context:** FR-002/FR-007 require removing user-supplied API keys.

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A (Recommended)** | Server-side proxy with provider key in env vars | Simple; reuses existing Alpha Vantage logic; key hidden from client | Rate limits shared across all users; cost scales with usage |
| B | Aggregate from multiple free sources | No single-provider dependency; redundancy | Complex integration; inconsistent data quality; maintenance burden |
| C | Proprietary data partnership | High quality; no rate limits | Cost; legal/contractual; long setup time |

**Recommendation:** Option A initially; upgrade to B for redundancy if rate limits become a problem.

### ALT-004: Workflow Architecture
**Context:** FR-006 requires multi-step workflow; current app has only `'landing' | 'workspace'`.

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A (Recommended)** | State-machine in App.tsx (e.g., `useReducer` with step enum) | Simple; no new dependencies; colocated with existing state; testable | Larger App.tsx; manual transition logic |
| B | URL-based routing (React Router) | Deep-linkable steps; browser back/forward; SEO-friendly | New dependency; routing complexity for SPA; bundle size increase |
| C | Multi-page wizard library (react-step-wizard) | Pre-built transitions; animation support | External dependency; less control; bundle size |

**Recommendation:** Option A — `useReducer` with a 4-step state machine. Keeps the app simple and dependency-free.

### ALT-005: Rewrite vs. Incremental
**Context:** The scope of changes (new backend, new workflow, new AI) might suggest a rewrite.

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A (Recommended)** | Incremental: add serverless functions, new components, extend state | Low risk; preserves tested logic; shippable in phases | May accumulate tech debt; older patterns alongside new |
| B | Full rewrite with new architecture (Next.js App Router) | Clean architecture; SSR; built-in API routes; modern patterns | High risk; loses tested code; longer timeline; learning curve |

**Recommendation:** Option A — incremental evolution. The existing utils are solid and tested; the changes are additive (new API layer, new UI components, extended state machine).

## 11. Glossary

| Term | Definition |
|------|-----------|
| DCF | Discounted Cash Flow — valuation method estimating present value of future cash flows |
| WACC | Weighted Average Cost of Capital — discount rate used in DCF |
| FCFF | Free Cash Flow to Firm — cash available to all capital providers |
| Enterprise Value | Total value of a company's operations (debt + equity) |
| Equity Value | Enterprise Value minus net debt; value attributable to shareholders |
| Implied Share Price | Equity Value divided by shares outstanding |
| NL | Natural Language — free-form human text input |
| LLM | Large Language Model — AI system for text understanding/generation |
| Edge Function | Serverless function running at CDN edge nodes (no cold start) |
| TTL | Time-To-Live — cache expiration duration |
