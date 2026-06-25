import { describe, it, expect, vi, afterEach } from 'vitest';
import { AlphaVantageProvider } from '../api/lib/marketDataProvider';

describe('AlphaVantageProvider', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  function setup() {
    vi.stubEnv('ALPHAVANTAGE_API_KEY', 'test-key');
    const mockFetch = vi.fn();
    vi.stubGlobal('fetch', mockFetch);
    const provider = new AlphaVantageProvider({ retryDelayMs: 0 });
    return { provider, mockFetch };
  }

  describe('fetchBeta', () => {
    it('returns ResearchDataSource with correct value, confidence, and source on success', async () => {
      const { provider, mockFetch } = setup();
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ Beta: '1.25' }),
      });

      const result = await provider.fetchBeta('AAPL');

      expect(result.value).toBe(1.25);
      expect(result.confidence).toBe('high');
      expect(result.source).toBe('Alpha Vantage (OVERVIEW)');
      expect(result.retrievedAt).toBeTruthy();
      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(mockFetch.mock.calls[0][0]).toContain('OVERVIEW');
      expect(mockFetch.mock.calls[0][0]).toContain('symbol=AAPL');
    });

    it('retries on rate-limit Note then returns fallback after max retries', async () => {
      const { provider, mockFetch } = setup();
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ Note: 'Thank you for using Alpha Vantage...' }),
      });

      const result = await provider.fetchBeta('AAPL');

      expect(result.source).toBe('default');
      expect(result.confidence).toBe('low');
      // Initial call + 3 retries = 4 total
      expect(mockFetch).toHaveBeenCalledTimes(4);
    });

    it('retries on network error then returns fallback', async () => {
      const { provider, mockFetch } = setup();
      mockFetch.mockRejectedValue(new Error('Network failure'));

      const result = await provider.fetchBeta('MSFT');

      expect(result.source).toBe('default');
      expect(result.confidence).toBe('low');
      expect(mockFetch).toHaveBeenCalledTimes(4);
    });

    it('retries on non-ok response then returns fallback', async () => {
      const { provider, mockFetch } = setup();
      mockFetch.mockResolvedValue({ ok: false, status: 500 });

      const result = await provider.fetchBeta('GOOG');

      expect(result.source).toBe('default');
      expect(result.confidence).toBe('low');
      expect(mockFetch).toHaveBeenCalledTimes(4);
    });

    it('returns fallback when Beta value is NaN', async () => {
      const { provider, mockFetch } = setup();
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ Beta: 'N/A' }),
      });

      const result = await provider.fetchBeta('AAPL');

      expect(result.source).toBe('default');
      expect(result.confidence).toBe('low');
    });

    it('retries on Error Message response then returns fallback', async () => {
      const { provider, mockFetch } = setup();
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ 'Error Message': 'Invalid API call' }),
      });

      const result = await provider.fetchBeta('AAPL');

      expect(result.source).toBe('default');
      expect(result.confidence).toBe('low');
      expect(mockFetch).toHaveBeenCalledTimes(4);
    });
  });

  describe('fetchRiskFreeRate', () => {
    it('returns ResearchDataSource with percent-to-decimal conversion', async () => {
      const { provider, mockFetch } = setup();
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: [{ value: '4.25' }] }),
      });

      const result = await provider.fetchRiskFreeRate();

      expect(result.value).toBeCloseTo(0.0425);
      expect(result.confidence).toBe('high');
      expect(result.source).toBe('Alpha Vantage (10Y Treasury Yield)');
      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(mockFetch.mock.calls[0][0]).toContain('TREASURY_YIELD');
    });

    it('retries on rate-limit then returns fallback', async () => {
      const { provider, mockFetch } = setup();
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ Note: 'Rate limit hit' }),
      });

      const result = await provider.fetchRiskFreeRate();

      expect(result.source).toBe('default');
      expect(result.confidence).toBe('low');
      expect(mockFetch).toHaveBeenCalledTimes(4);
    });

    it('returns fallback when treasury value is NaN', async () => {
      const { provider, mockFetch } = setup();
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ data: [{ value: '.' }] }),
      });

      const result = await provider.fetchRiskFreeRate();

      expect(result.source).toBe('default');
      expect(result.confidence).toBe('low');
    });

    it('returns fallback on invalid JSON structure', async () => {
      const { provider, mockFetch } = setup();
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ unexpected: 'shape' }),
      });

      const result = await provider.fetchRiskFreeRate();

      expect(result.source).toBe('default');
      expect(result.confidence).toBe('low');
    });
  });

  describe('fetchERP', () => {
    it('returns Damodaran default without calling fetch', async () => {
      const { provider, mockFetch } = setup();

      const result = await provider.fetchERP();

      expect(result.value).toBe(0.055);
      expect(result.confidence).toBe('low');
      expect(result.source).toBe('Default estimate (Damodaran)');
      expect(result.retrievedAt).toBeTruthy();
      expect(mockFetch).not.toHaveBeenCalled();
    });
  });

  describe('missing API key', () => {
    it('returns fallback when ALPHAVANTAGE_API_KEY is not set', async () => {
      vi.stubEnv('ALPHAVANTAGE_API_KEY', '');
      const mockFetch = vi.fn();
      vi.stubGlobal('fetch', mockFetch);
      const provider = new AlphaVantageProvider({ retryDelayMs: 0 });

      const result = await provider.fetchBeta('AAPL');

      expect(result.source).toBe('default');
      expect(result.confidence).toBe('low');
      expect(mockFetch).not.toHaveBeenCalled();
    });
  });
});
