import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fetchMarketData } from '../src/utils/researchApi';

describe('fetchMarketData', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.useRealTimers();
  });

  it('parses beta and risk-free rate into ResearchDataSource with correct conversion', async () => {
    globalThis.fetch = vi.fn((url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString();
      if (urlStr.includes('OVERVIEW')) {
        return Promise.resolve(new Response(JSON.stringify({ Beta: '1.25' })));
      }
      if (urlStr.includes('TREASURY_YIELD')) {
        return Promise.resolve(new Response(JSON.stringify({ data: [{ value: '4.25' }] })));
      }
      return Promise.resolve(new Response(JSON.stringify({})));
    }) as unknown as typeof fetch;

    const result = await fetchMarketData('AAPL', 'test-key');

    expect(result.data.beta).toBeDefined();
    expect(result.data.beta!.value).toBe(1.25);
    expect(result.data.beta!.source).toBe('Alpha Vantage (OVERVIEW)');
    expect(result.data.beta!.confidence).toBe('high');
    expect(result.data.beta!.retrievedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);

    expect(result.data.riskFreeRate).toBeDefined();
    expect(result.data.riskFreeRate!.value).toBe(0.0425);
    expect(result.data.riskFreeRate!.source).toBe('Alpha Vantage (10Y Treasury Yield)');
    expect(result.data.riskFreeRate!.confidence).toBe('high');

    expect(result.errors).toHaveLength(0);
  });

  it('always returns ERP default (0.055, low confidence)', async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({})))
    ) as unknown as typeof fetch;

    const result = await fetchMarketData('AAPL', 'test-key');

    expect(result.data.equityRiskPremium).toBeDefined();
    expect(result.data.equityRiskPremium!.value).toBe(0.055);
    expect(result.data.equityRiskPremium!.source).toBe('Default estimate (Damodaran)');
    expect(result.data.equityRiskPremium!.confidence).toBe('low');
    expect(result.data.equityRiskPremium!.retrievedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it('returns empty data with error when apiKey is empty', async () => {
    globalThis.fetch = vi.fn() as unknown as typeof fetch;

    const result = await fetchMarketData('AAPL', '');

    expect(result.data).toEqual({});
    expect(result.errors).toContain('API key required');
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('handles fetch rejection for one field without killing others', async () => {
    globalThis.fetch = vi.fn((url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString();
      if (urlStr.includes('OVERVIEW')) {
        return Promise.reject(new Error('Network error'));
      }
      if (urlStr.includes('TREASURY_YIELD')) {
        return Promise.resolve(new Response(JSON.stringify({ data: [{ value: '3.50' }] })));
      }
      return Promise.resolve(new Response(JSON.stringify({})));
    }) as unknown as typeof fetch;

    const result = await fetchMarketData('AAPL', 'test-key');

    expect(result.data.beta).toBeUndefined();
    expect(result.data.riskFreeRate).toBeDefined();
    expect(result.data.riskFreeRate!.value).toBe(0.035);
    expect(result.data.equityRiskPremium).toBeDefined();
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.errors.some((e) => e.includes('beta'))).toBe(true);
  });

  it('handles Alpha Vantage rate-limit response (Note field) as per-field error', async () => {
    globalThis.fetch = vi.fn((url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString();
      if (urlStr.includes('OVERVIEW')) {
        return Promise.resolve(new Response(JSON.stringify({ Note: 'API rate limit reached' })));
      }
      if (urlStr.includes('TREASURY_YIELD')) {
        return Promise.resolve(new Response(JSON.stringify({ Note: 'API rate limit reached' })));
      }
      return Promise.resolve(new Response(JSON.stringify({})));
    }) as unknown as typeof fetch;

    const result = await fetchMarketData('AAPL', 'test-key');

    expect(result.data.beta).toBeUndefined();
    expect(result.data.riskFreeRate).toBeUndefined();
    // ERP is always returned (default constant, no API call)
    expect(result.data.equityRiskPremium).toBeDefined();
    expect(result.errors.length).toBe(2);
    expect(result.errors.some((e) => e.includes('beta'))).toBe(true);
    expect(result.errors.some((e) => e.includes('riskFreeRate'))).toBe(true);
  });

  it('handles malformed Beta value (undefined/NaN) as per-field error', async () => {
    globalThis.fetch = vi.fn((url: string | URL | Request) => {
      const urlStr = typeof url === 'string' ? url : url.toString();
      if (urlStr.includes('OVERVIEW')) {
        return Promise.resolve(new Response(JSON.stringify({ Beta: 'None' })));
      }
      if (urlStr.includes('TREASURY_YIELD')) {
        return Promise.resolve(new Response(JSON.stringify({ data: [{ value: '4.00' }] })));
      }
      return Promise.resolve(new Response(JSON.stringify({})));
    }) as unknown as typeof fetch;

    const result = await fetchMarketData('AAPL', 'test-key');

    expect(result.data.beta).toBeUndefined();
    expect(result.data.riskFreeRate).toBeDefined();
    expect(result.data.riskFreeRate!.value).toBe(0.04);
    expect(result.errors.some((e) => e.includes('beta'))).toBe(true);
  });
});
