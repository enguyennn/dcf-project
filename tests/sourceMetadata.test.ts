import { describe, it, expect } from 'vitest';
import { sourceBadgeStyle, summarizeSources } from '../src/components/sourceMetadata';
import type { AssumptionMetadata } from '../src/models/aiTypes';

describe('sourceBadgeStyle', () => {
  it('returns blue for market-data', () => {
    const result = sourceBadgeStyle('market-data');
    expect(result.label).toBe('Market Data');
    expect(result.className).toContain('blue');
  });

  it('returns purple for ai-inferred', () => {
    const result = sourceBadgeStyle('ai-inferred');
    expect(result.label).toBe('AI Inferred');
    expect(result.className).toContain('purple');
  });

  it('returns green for industry-benchmark', () => {
    const result = sourceBadgeStyle('industry-benchmark');
    expect(result.label).toBe('Industry Benchmark');
    expect(result.className).toContain('green');
  });

  it('returns gray for default', () => {
    const result = sourceBadgeStyle('default');
    expect(result.label).toBe('Default');
    expect(result.className).toContain('gray');
  });

  it('returns orange for user-provided', () => {
    const result = sourceBadgeStyle('user-provided');
    expect(result.label).toBe('User Provided');
    expect(result.className).toContain('orange');
  });
});

describe('summarizeSources', () => {
  const meta = (source: AssumptionMetadata['source']): AssumptionMetadata => ({
    field: 'test',
    value: 1,
    source,
    confidence: 'medium',
    rationale: '',
  });

  it('returns correct counts for mixed metadata', () => {
    const input: AssumptionMetadata[] = [
      meta('ai-inferred'),
      meta('ai-inferred'),
      meta('ai-inferred'),
      meta('market-data'),
      meta('market-data'),
      meta('default'),
    ];
    const result = summarizeSources(input);
    expect(result).toEqual([
      { source: 'ai-inferred', count: 3, label: 'AI Inferred' },
      { source: 'market-data', count: 2, label: 'Market Data' },
      { source: 'default', count: 1, label: 'Default' },
    ]);
  });

  it('omits zero-count sources', () => {
    const input: AssumptionMetadata[] = [meta('user-provided')];
    const result = summarizeSources(input);
    expect(result).toHaveLength(1);
    expect(result[0].source).toBe('user-provided');
    expect(result.find((s) => s.source === 'ai-inferred')).toBeUndefined();
  });

  it('returns empty array for empty metadata', () => {
    expect(summarizeSources([])).toEqual([]);
  });

  it('maintains stable order regardless of input order', () => {
    const input: AssumptionMetadata[] = [
      meta('user-provided'),
      meta('default'),
      meta('ai-inferred'),
    ];
    const result = summarizeSources(input);
    expect(result.map((s) => s.source)).toEqual(['ai-inferred', 'default', 'user-provided']);
  });
});
