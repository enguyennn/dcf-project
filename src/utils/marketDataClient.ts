import type { MarketDataResponse } from '../models/aiTypes';

/**
 * Fetches market data from the server-side proxy endpoint.
 * No API key required — the key is managed server-side.
 */
export async function fetchMarketDataFromServer(ticker: string): Promise<MarketDataResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);

  try {
    const res = await fetch(
      `/api/market-data?ticker=${encodeURIComponent(ticker)}`,
      { signal: controller.signal }
    );
    clearTimeout(timer);

    if (!res.ok) {
      const body = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      return { data: {}, errors: [body.error || `HTTP ${res.status}`] };
    }

    const json: MarketDataResponse = await res.json();
    return json;
  } catch (e: unknown) {
    clearTimeout(timer);
    const msg = e instanceof Error ? e.message : 'Unknown error';
    return { data: {}, errors: [msg] };
  }
}
