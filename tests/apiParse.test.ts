import { describe, it, expect, vi } from 'vitest';
import { handleParse } from '../api/parse';
import type { LLMProvider } from '../lib/llmProvider';
import type { ParseResponse } from '../src/models/aiTypes';

function createFakeProvider(
  response: ParseResponse
): LLMProvider & { parseFinancialText: ReturnType<typeof vi.fn> } {
  return {
    parseFinancialText: vi.fn().mockResolvedValue(response),
  };
}

describe('handleParse', () => {
  it('(1) complete extraction passes through values', async () => {
    const provider = createFakeProvider({
      assumptions: {
        revenue: 50_000_000,
        revenueGrowthRate: 0.3,
        operatingMarginRate: 0.7,
        company: { industry: 'SaaS', companyName: '', currency: 'USD' },
      },
      metadata: [
        { field: 'revenue', value: 50_000_000, source: 'ai-inferred', confidence: 'high', rationale: 'Extracted' },
        { field: 'revenueGrowthRate', value: 0.3, source: 'ai-inferred', confidence: 'medium', rationale: 'Inferred' },
        { field: 'operatingMarginRate', value: 0.7, source: 'ai-inferred', confidence: 'medium', rationale: 'Inferred' },
      ],
    });

    const result = await handleParse(
      { text: 'A $50M SaaS company growing 30% with 70% margins' },
      provider,
    );

    expect(result.status).toBe(200);
    const body = result.body as ParseResponse;
    expect(body.assumptions.revenue).toBe(50_000_000);
    expect(body.assumptions.revenueGrowthRate).toBe(0.3);
    expect(body.assumptions.operatingMarginRate).toBe(0.7);
    expect(body.assumptions.company?.industry).toBe('SaaS');
    expect(body.metadata.length).toBeGreaterThan(0);
    expect(body.followUp).toBeUndefined();
    expect(provider.parseFinancialText).toHaveBeenCalledOnce();
  });

  it('(2) partial extraction includes follow-up for missing revenue', async () => {
    const provider = createFakeProvider({
      assumptions: { operatingMarginRate: 0.7 },
      metadata: [
        { field: 'operatingMarginRate', value: 0.7, source: 'ai-inferred', confidence: 'medium', rationale: 'Inferred' },
      ],
    });

    const result = await handleParse(
      { text: 'Operating margins around 70%' },
      provider,
    );

    expect(result.status).toBe(200);
    const body = result.body as ParseResponse;
    expect(body.assumptions.operatingMarginRate).toBe(0.7);
    expect(body.followUp).toBeDefined();
    expect(body.followUp!.some((q) => q.toLowerCase().includes('revenue'))).toBe(true);
    expect(provider.parseFinancialText).toHaveBeenCalledOnce();
  });

  it('(3) empty extraction returns follow-up questions', async () => {
    const provider = createFakeProvider({
      assumptions: {},
      metadata: [],
    });

    const result = await handleParse(
      { text: 'Hello world this is nonsense text' },
      provider,
    );

    expect(result.status).toBe(200);
    const body = result.body as ParseResponse;
    expect(body.assumptions).toEqual({});
    expect(body.metadata).toEqual([]);
    expect(body.followUp).toBeDefined();
    expect(body.followUp!.length).toBeGreaterThan(0);
    expect(provider.parseFinancialText).toHaveBeenCalledOnce();
  });

  it('(4) percentages are auto-corrected to decimals', async () => {
    const provider = createFakeProvider({
      assumptions: {
        revenueGrowthRate: 30,
        operatingMarginRate: 70,
      },
      metadata: [
        { field: 'revenueGrowthRate', value: 30, source: 'ai-inferred', confidence: 'medium', rationale: 'Inferred' },
        { field: 'operatingMarginRate', value: 70, source: 'ai-inferred', confidence: 'medium', rationale: 'Inferred' },
      ],
    });

    const result = await handleParse(
      { text: 'Growth rate 30%, margins 70%' },
      provider,
    );

    expect(result.status).toBe(200);
    const body = result.body as ParseResponse;
    expect(body.assumptions.revenueGrowthRate).toBeCloseTo(0.3);
    expect(body.assumptions.operatingMarginRate).toBeCloseTo(0.7);
    // revenue missing → follow-up
    expect(body.followUp).toBeDefined();
    expect(body.followUp!.some((q) => q.toLowerCase().includes('revenue'))).toBe(true);
    expect(provider.parseFinancialText).toHaveBeenCalledOnce();
  });

  it('(5) input exceeding 2000 chars returns 400 without calling provider', async () => {
    const provider = createFakeProvider({
      assumptions: {},
      metadata: [],
    });

    const longText = 'A'.repeat(2001);
    const result = await handleParse({ text: longText }, provider);

    expect(result.status).toBe(400);
    expect((result.body as { error: string }).error).toBeDefined();
    expect(provider.parseFinancialText).not.toHaveBeenCalled();
  });
});
