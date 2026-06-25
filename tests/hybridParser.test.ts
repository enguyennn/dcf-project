import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../src/utils/aiClient', () => ({
  parseWithAI: vi.fn(),
}));

import { parseWithAI } from '../src/utils/aiClient';
import { hybridParse } from '../src/utils/hybridParser';
import type { ParseResponse } from '../src/models/aiTypes';

const mockParseWithAI = vi.mocked(parseWithAI);

describe('hybridParse', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('structured-only input stays client-side — parseWithAI not called', async () => {
    const result = await hybridParse('Revenue: 1000000\nOperating Income: 150000');

    expect(mockParseWithAI).not.toHaveBeenCalled();
    expect(result.parsed.revenue).toBe(1000000);
    expect(result.parsed.operatingIncome).toBe(150000);
    expect(result.metadata).toHaveLength(2);
    expect(result.metadata.every((m) => m.source === 'user-provided')).toBe(true);
    expect(result.metadata.every((m) => m.confidence === 'high')).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it('NL-only input calls API with full text', async () => {
    const aiResponse: ParseResponse = {
      assumptions: { revenue: 50000000 },
      metadata: [
        {
          field: 'revenue',
          value: 50000000,
          source: 'ai-inferred',
          confidence: 'medium',
          rationale: 'Estimated from description',
        },
      ],
    };
    mockParseWithAI.mockResolvedValue(aiResponse);

    const result = await hybridParse('A fast growing SaaS company');

    expect(mockParseWithAI).toHaveBeenCalledOnce();
    expect(mockParseWithAI).toHaveBeenCalledWith('A fast growing SaaS company');
    expect(result.parsed.revenue).toBe(50000000);
    expect(result.metadata).toHaveLength(1);
    expect(result.metadata[0].source).toBe('ai-inferred');
    expect(result.errors).toEqual([]);
  });

  it('mixed input partially routes — regex wins on conflict', async () => {
    const aiResponse: ParseResponse = {
      assumptions: { revenue: 9999999, operatingMarginRate: 0.25 },
      metadata: [
        {
          field: 'revenue',
          value: 9999999,
          source: 'ai-inferred',
          confidence: 'medium',
          rationale: 'AI estimate',
        },
        {
          field: 'operatingMarginRate',
          value: 0.25,
          source: 'ai-inferred',
          confidence: 'medium',
          rationale: 'Inferred from moat description',
        },
      ],
    };
    mockParseWithAI.mockResolvedValue(aiResponse);

    const result = await hybridParse('Revenue: 1000000\nstrong moat and pricing power');

    // parseWithAI called with ONLY the unmatched line
    expect(mockParseWithAI).toHaveBeenCalledOnce();
    expect(mockParseWithAI).toHaveBeenCalledWith('strong moat and pricing power');

    // Regex field wins on conflict
    expect(result.parsed.revenue).toBe(1000000);
    // AI-only field added
    expect(result.parsed.operatingMarginRate).toBe(0.25);

    // Metadata: revenue is user-provided (regex wins), operatingMarginRate is ai-inferred
    const revenueMeta = result.metadata.find((m) => m.field === 'revenue');
    expect(revenueMeta?.source).toBe('user-provided');
    const marginMeta = result.metadata.find((m) => m.field === 'operatingMarginRate');
    expect(marginMeta?.source).toBe('ai-inferred');

    // "strong moat..." is NOT in errors
    expect(result.errors).toEqual([]);
    expect(result.errors).not.toContain('strong moat and pricing power');
  });

  it('AI call failure degrades gracefully', async () => {
    mockParseWithAI.mockRejectedValue(new Error('Network timeout'));

    const result = await hybridParse('A fast growing SaaS company');

    expect(mockParseWithAI).toHaveBeenCalledOnce();
    // No regex matches, so parsed is empty
    expect(Object.keys(result.parsed)).toHaveLength(0);
    // errors contains the thrown message
    expect(result.errors).toContain('Network timeout');
  });
});
