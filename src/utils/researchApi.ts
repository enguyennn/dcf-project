/**
 * @deprecated This module's logic has been moved server-side to api/lib/marketDataProvider.ts (FR-007.5).
 * The client should use src/utils/marketDataClient.ts instead.
 * Retained for reference and existing test coverage.
 */
import type { ResearchDataSource } from '../models/financialTypes';

type ResearchField = 'riskFreeRate' | 'beta' | 'equityRiskPremium';

export interface FetchMarketDataResult {
  data: Partial<Record<ResearchField, ResearchDataSource>>;
  errors: string[];
}

export async function fetchMarketData(
  ticker: string,
  apiKey: string,
  timeoutMs = 8000
): Promise<FetchMarketDataResult> {
  const errors: string[] = [];
  const data: Partial<Record<ResearchField, ResearchDataSource>> = {};

  if (!apiKey) {
    return { data: {}, errors: ['API key required'] };
  }

  const now = new Date().toISOString();

  // Beta from OVERVIEW endpoint
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const res = await fetch(
      `https://www.alphavantage.co/query?function=OVERVIEW&symbol=${encodeURIComponent(ticker)}&apikey=${apiKey}`,
      { signal: controller.signal }
    );
    clearTimeout(timer);
    const json = await res.json();

    if (json?.Note || json?.['Error Message']) {
      errors.push('beta: ' + (json.Note || json['Error Message']));
    } else {
      const betaVal = Number(json?.Beta);
      if (Number.isNaN(betaVal)) {
        errors.push('beta: invalid or missing value from provider');
      } else {
        data.beta = {
          value: betaVal,
          source: 'Alpha Vantage (OVERVIEW)',
          retrievedAt: now,
          confidence: 'high',
        };
      }
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Unknown error';
    errors.push(`beta: ${msg}`);
  }

  // Risk-free rate from TREASURY_YIELD endpoint
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const res = await fetch(
      `https://www.alphavantage.co/query?function=TREASURY_YIELD&interval=monthly&maturity=10year&apikey=${apiKey}`,
      { signal: controller.signal }
    );
    clearTimeout(timer);
    const json = await res.json();

    if (json?.Note || json?.['Error Message']) {
      errors.push('riskFreeRate: ' + (json.Note || json['Error Message']));
    } else {
      const rateStr = json?.data?.[0]?.value;
      const rateVal = Number(rateStr);
      if (Number.isNaN(rateVal)) {
        errors.push('riskFreeRate: invalid or missing value from provider');
      } else {
        data.riskFreeRate = {
          value: rateVal / 100,
          source: 'Alpha Vantage (10Y Treasury Yield)',
          retrievedAt: now,
          confidence: 'high',
        };
      }
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Unknown error';
    errors.push(`riskFreeRate: ${msg}`);
  }

  // ERP — no public API, use documented default constant
  data.equityRiskPremium = {
    value: 0.055,
    source: 'Default estimate (Damodaran)',
    retrievedAt: now,
    confidence: 'low',
  };

  return { data, errors };
}
