import type { ResearchDataSource } from '../../src/models/financialTypes';

export interface MarketDataProvider {
  fetchBeta(ticker: string): Promise<ResearchDataSource>;
  fetchRiskFreeRate(): Promise<ResearchDataSource>;
  fetchERP(): Promise<ResearchDataSource>;
}

interface AlphaVantageProviderOptions {
  retryDelayMs?: number;
}

const MAX_RETRIES = 3;
const DEFAULT_RETRY_DELAY_MS = 300;

export class AlphaVantageProvider implements MarketDataProvider {
  private readonly retryDelayMs: number;

  constructor(opts?: AlphaVantageProviderOptions) {
    this.retryDelayMs = opts?.retryDelayMs ?? DEFAULT_RETRY_DELAY_MS;
  }

  async fetchBeta(ticker: string): Promise<ResearchDataSource> {
    const apiKey = process.env.ALPHAVANTAGE_API_KEY;
    if (!apiKey) {
      return this.fallback(0, 'beta');
    }

    const url = `https://www.alphavantage.co/query?function=OVERVIEW&symbol=${encodeURIComponent(ticker)}&apikey=${apiKey}`;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const res = await fetch(url);
        if (!res.ok) {
          await this.delay(attempt);
          continue;
        }
        const json = (await res.json()) as Record<string, unknown>;

        if (json.Note || json['Error Message']) {
          await this.delay(attempt);
          continue;
        }

        const betaVal = Number(json.Beta);
        if (Number.isNaN(betaVal)) {
          return this.fallback(0, 'beta');
        }

        return {
          value: betaVal,
          source: 'Alpha Vantage (OVERVIEW)',
          retrievedAt: new Date().toISOString(),
          confidence: 'high',
        };
      } catch {
        await this.delay(attempt);
        continue;
      }
    }

    return this.fallback(0, 'beta');
  }

  async fetchRiskFreeRate(): Promise<ResearchDataSource> {
    const apiKey = process.env.ALPHAVANTAGE_API_KEY;
    if (!apiKey) {
      return this.fallback(0.04, 'riskFreeRate');
    }

    const url = `https://www.alphavantage.co/query?function=TREASURY_YIELD&interval=monthly&maturity=10year&apikey=${apiKey}`;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const res = await fetch(url);
        if (!res.ok) {
          await this.delay(attempt);
          continue;
        }
        const json = (await res.json()) as Record<string, unknown>;

        if (json.Note || json['Error Message']) {
          await this.delay(attempt);
          continue;
        }

        const dataArr = json.data as Array<{ value: string }> | undefined;
        const rateStr = dataArr?.[0]?.value;
        const rateVal = Number(rateStr);
        if (Number.isNaN(rateVal)) {
          return this.fallback(0.04, 'riskFreeRate');
        }

        return {
          value: rateVal / 100,
          source: 'Alpha Vantage (10Y Treasury Yield)',
          retrievedAt: new Date().toISOString(),
          confidence: 'high',
        };
      } catch {
        await this.delay(attempt);
        continue;
      }
    }

    return this.fallback(0.04, 'riskFreeRate');
  }

  async fetchERP(): Promise<ResearchDataSource> {
    return {
      value: 0.055,
      source: 'Default estimate (Damodaran)',
      retrievedAt: new Date().toISOString(),
      confidence: 'low',
    };
  }

  private fallback(value: number, _field: string): ResearchDataSource {
    return {
      value,
      source: 'default',
      retrievedAt: new Date().toISOString(),
      confidence: 'low',
    };
  }

  private delay(attempt: number): Promise<void> {
    if (this.retryDelayMs === 0) return Promise.resolve();
    const ms = this.retryDelayMs * Math.pow(2, attempt);
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
