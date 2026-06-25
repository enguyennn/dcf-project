/**
 * ITEM-050 — Performance validation: p95 ≤ 8 seconds.
 *
 * RECONCILIATION: In the vitest/node environment there is no real network
 * and `parseWithAI` calls `fetch('/api/parse')` which does not exist.
 * Therefore we MUST mock `parseWithAI` (with a small artificial delay to
 * simulate latency). This measures the STRUCTURAL/local pipeline latency
 * (hybridParse + mergeAssumptions + runFullDCF), NOT the real network
 * round-trip to `/api/parse`. The real-network p95 is validated separately
 * via Vercel/manual testing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../src/utils/aiClient', () => ({
  parseWithAI: vi.fn(),
}));

import { parseWithAI } from '../../src/utils/aiClient';
import { hybridParse } from '../../src/utils/hybridParser';
import { mergeAssumptions } from '../../src/utils/assumptionEngine';
import { runFullDCF } from '../../src/utils/dcfCalculations';
import type { ParseResponse } from '../../src/models/aiTypes';

const mockParseWithAI = vi.mocked(parseWithAI);

const P95_BUDGET_MS = 8_000; // 8 seconds
const NUM_RUNS = 25; // > 20 as required
const SIMULATED_AI_DELAY_MS = 50; // small artificial latency to simulate network

const AI_RESPONSE: ParseResponse = {
  assumptions: {
    revenue: 100_000_000,
    operatingIncome: 20_000_000,
    revenueGrowthRate: 0.15,
    operatingMarginRate: 0.20,
    sharesOutstanding: 50_000_000,
    netDebt: 10_000_000,
    depreciationAmortization: 5_000_000,
    capitalExpenditures: 8_000_000,
    changeInNWC: 2_000_000,
  },
  metadata: [
    { field: 'revenue', value: 100_000_000, source: 'ai-inferred', confidence: 'medium', rationale: 'Estimated' },
  ],
};

const INPUTS = [
  'A mid-size SaaS company growing 30% YoY with 70% gross margins',
  'An e-commerce retailer doing $200M in annual sales',
  'A biotech startup with $50M in funding and no revenue',
  'A fintech processor handling $10B volume',
  'Enterprise cloud provider with $1B ARR',
];

describe('ITEM-050: p95 pipeline latency ≤ 8s', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockParseWithAI.mockImplementation(async () => {
      await new Promise((resolve) => setTimeout(resolve, SIMULATED_AI_DELAY_MS));
      return AI_RESPONSE;
    });
  });

  it(`p95 over ${NUM_RUNS} runs is under ${P95_BUDGET_MS}ms`, { timeout: 30_000 }, async () => {
    const timings: number[] = [];

    for (let i = 0; i < NUM_RUNS; i++) {
      const input = INPUTS[i % INPUTS.length];
      const start = performance.now();

      const result = await hybridParse(input);
      const inputs = mergeAssumptions(result.parsed);
      runFullDCF(inputs);

      const elapsed = performance.now() - start;
      timings.push(elapsed);
    }

    timings.sort((a, b) => a - b);
    const p95Index = Math.ceil(0.95 * timings.length) - 1;
    const p95 = timings[p95Index];

    // Log for visibility
    console.log(`Performance results (${NUM_RUNS} runs):`);
    console.log(`  min: ${timings[0].toFixed(1)}ms`);
    console.log(`  median: ${timings[Math.floor(timings.length / 2)].toFixed(1)}ms`);
    console.log(`  p95: ${p95.toFixed(1)}ms`);
    console.log(`  max: ${timings[timings.length - 1].toFixed(1)}ms`);
    console.log(`  budget: ${P95_BUDGET_MS}ms`);

    expect(p95).toBeLessThan(P95_BUDGET_MS);
  });
});
