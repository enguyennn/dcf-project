import type { VercelRequest, VercelResponse } from '@vercel/node';
import { applyCors } from '../lib/cors';
import { checkRateLimit } from '../lib/rateLimiter';
import { validateTickerInput } from '../lib/validation';
import { AlphaVantageProvider } from '../lib/marketDataProvider';
import type { ResearchDataSource } from '../src/models/financialTypes';

/**
 * Simple in-memory cache for the treasury (risk-free) rate.
 * TTL: 1 hour. Shared across warm invocations on the same instance.
 */
let riskFreeCache: { value: ResearchDataSource; expiry: number } | null = null;
const CACHE_TTL_MS = 60 * 60 * 1000;

/**
 * Per-ticker beta cache. TTL: 1 hour. Key = ticker symbol (uppercased).
 */
const betaCache = new Map<string, { value: ResearchDataSource; expiry: number }>();

/**
 * GET /api/market-data?ticker=AAPL
 *
 * Response shape: MarketDataResponse = { data: { beta?, riskFreeRate?, equityRiskPremium? }, errors: string[] }
 */
export default async function handler(req: VercelRequest, res: VercelResponse): Promise<void> {
  if (applyCors(req, res)) return;

  if (req.method !== 'GET') {
    res.status(405).json({ error: 'Method not allowed', code: 'METHOD_NOT_ALLOWED' });
    return;
  }

  // Rate limiting — per-endpoint namespace
  const forwarded = req.headers['x-forwarded-for'];
  const ip = (typeof forwarded === 'string' ? forwarded.split(',')[0].trim() : '') || 'unknown';
  const { allowed, retryAfterSeconds } = checkRateLimit(`market-data:${ip}`, 20);
  if (!allowed) {
    res.setHeader('Retry-After', String(retryAfterSeconds));
    res.status(429).json({ error: 'Rate limit exceeded', code: 'RATE_LIMITED' });
    return;
  }

  // Validate ticker
  const tickerRaw = Array.isArray(req.query.ticker) ? req.query.ticker[0] : req.query.ticker;
  const validation = validateTickerInput({ ticker: tickerRaw });
  if (!validation.valid) {
    res.status(400).json({ error: validation.error, code: 'INVALID_INPUT' });
    return;
  }
  const { ticker } = validation;

  try {
    // Fetch market data
    const provider = new AlphaVantageProvider();
    const errors: string[] = [];

    const [beta, riskFreeRate, equityRiskPremium] = await Promise.all([
      getCachedBeta(provider, ticker).catch((e: unknown) => {
        errors.push(`beta: ${e instanceof Error ? e.message : 'Unknown error'}`);
        return undefined;
      }),
      getCachedRiskFreeRate(provider).catch((e: unknown) => {
        errors.push(`riskFreeRate: ${e instanceof Error ? e.message : 'Unknown error'}`);
        return undefined;
      }),
      provider.fetchERP().catch((e: unknown) => {
        errors.push(`equityRiskPremium: ${e instanceof Error ? e.message : 'Unknown error'}`);
        return undefined;
      }),
    ]);

    res.status(200).json({
      data: {
        ...(beta && { beta }),
        ...(riskFreeRate && { riskFreeRate }),
        ...(equityRiskPremium && { equityRiskPremium }),
      },
      errors,
    });
  } catch (err: unknown) {
    console.error('market-data handler error:', err);
    res.status(500).json({ error: 'Internal server error', code: 'INTERNAL_ERROR' });
  }
}

async function getCachedBeta(provider: AlphaVantageProvider, ticker: string): Promise<ResearchDataSource> {
  const now = Date.now();
  const cached = betaCache.get(ticker);
  if (cached && now < cached.expiry) {
    return cached.value;
  }
  const result = await provider.fetchBeta(ticker);
  betaCache.set(ticker, { value: result, expiry: now + CACHE_TTL_MS });
  return result;
}

async function getCachedRiskFreeRate(provider: AlphaVantageProvider): Promise<ResearchDataSource> {
  const now = Date.now();
  if (riskFreeCache && now < riskFreeCache.expiry) {
    return riskFreeCache.value;
  }
  const result = await provider.fetchRiskFreeRate();
  riskFreeCache = { value: result, expiry: now + CACHE_TTL_MS };
  return result;
}
