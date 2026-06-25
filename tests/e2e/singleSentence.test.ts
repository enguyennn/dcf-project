/**
 * ITEM-047 — Single-sentence-to-model end-to-end validation.
 *
 * Proves: a single NL sentence flows through hybridParse → mergeAssumptions →
 * runFullDCF and produces a non-zero enterprise/equity value.
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

describe('ITEM-047: Single sentence → full DCF model', () => {
  const INPUT = 'A mid-size SaaS company growing 30% YoY with 70% gross margins';

  beforeEach(() => {
    vi.resetAllMocks();

    const aiResponse: ParseResponse = {
      assumptions: {
        revenue: 50_000_000,
        revenueGrowthRate: 0.30,
        operatingMarginRate: 0.55, // plausible operating margin for 70% gross margin SaaS
        operatingIncome: 27_500_000,
        sharesOutstanding: 10_000_000,
        netDebt: 5_000_000,
        company: { companyName: 'Mid-size SaaS Co', currency: 'USD', industry: 'SaaS' },
      },
      metadata: [
        { field: 'revenue', value: 50_000_000, source: 'ai-inferred', confidence: 'medium', rationale: 'Estimated mid-size SaaS revenue' },
        { field: 'revenueGrowthRate', value: 0.30, source: 'ai-inferred', confidence: 'high', rationale: 'Stated 30% YoY' },
        { field: 'operatingMarginRate', value: 0.55, source: 'ai-inferred', confidence: 'medium', rationale: 'Derived from 70% gross margin less SaaS opex' },
        { field: 'operatingIncome', value: 27_500_000, source: 'ai-inferred', confidence: 'medium', rationale: '55% of $50M' },
        { field: 'sharesOutstanding', value: 10_000_000, source: 'ai-inferred', confidence: 'low', rationale: 'Assumed typical share count' },
        { field: 'netDebt', value: 5_000_000, source: 'ai-inferred', confidence: 'low', rationale: 'Assumed modest leverage' },
      ],
    };
    mockParseWithAI.mockResolvedValue(aiResponse);
  });

  it('hybridParse returns all required fields populated', async () => {
    const result = await hybridParse(INPUT);

    expect(result.errors).toEqual([]);
    expect(result.parsed.revenue).toBeGreaterThan(0);
    expect(result.parsed.revenueGrowthRate).toBe(0.30);
    expect(result.parsed.operatingMarginRate).toBeGreaterThan(0);
    expect(result.parsed.operatingIncome).toBeGreaterThan(0);
    expect(result.parsed.sharesOutstanding).toBeGreaterThan(0);
  });

  it('merged inputs produce non-zero enterpriseValue and equityValue', async () => {
    const result = await hybridParse(INPUT);
    const inputs = mergeAssumptions(result.parsed);
    const outputs = runFullDCF(inputs);

    expect(outputs.enterpriseValue).toBeGreaterThan(0);
    expect(outputs.equityValue).toBeGreaterThan(0);
    expect(outputs.impliedSharePrice).toBeGreaterThan(0);
  });

  it('full pipeline from sentence to valuation is deterministic', async () => {
    const result1 = await hybridParse(INPUT);
    const outputs1 = runFullDCF(mergeAssumptions(result1.parsed));

    const result2 = await hybridParse(INPUT);
    const outputs2 = runFullDCF(mergeAssumptions(result2.parsed));

    expect(outputs1.enterpriseValue).toBe(outputs2.enterpriseValue);
    expect(outputs1.equityValue).toBe(outputs2.equityValue);
  });
});
