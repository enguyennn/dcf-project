import type { VercelRequest, VercelResponse } from '@vercel/node';
import { applyCors } from './lib/cors';
import { checkRateLimit } from './lib/rateLimiter';
import { INDUSTRY_BENCHMARKS, lookupBenchmark } from '../src/data/industryBenchmarks';
import type { IndustryBenchmark } from '../src/models/aiTypes';

/**
 * In-memory cache for benchmark lookups. TTL: 24 hours.
 * Key = industry string (lowercased by lookupBenchmark).
 */
const benchmarkCache = new Map<string, { value: IndustryBenchmark; expiry: number }>();
const BENCHMARK_CACHE_TTL_MS = 24 * 60 * 60 * 1000;

export default function handler(req: VercelRequest, res: VercelResponse) {
  if (applyCors(req, res)) return;

  if (req.method !== 'GET') {
    res.status(405).json({ error: 'Method not allowed', code: 'METHOD_NOT_ALLOWED' });
    return;
  }

  const forwarded = req.headers['x-forwarded-for'];
  const ip = typeof forwarded === 'string'
    ? forwarded.split(',')[0].trim()
    : 'unknown';

  const { allowed, retryAfterSeconds } = checkRateLimit(`benchmarks:${ip}`, 60);
  if (!allowed) {
    res.setHeader('Retry-After', String(retryAfterSeconds));
    res.status(429).json({ error: 'Rate limit exceeded', code: 'RATE_LIMITED' });
    return;
  }

  try {
    const rawIndustry = req.query.industry;
    const industry = Array.isArray(rawIndustry) ? rawIndustry[0] : rawIndustry;

    const benchmark = industry ? getCachedBenchmark(industry) : undefined;

    if (benchmark) {
      res.status(200).json(benchmark);
    } else {
      res.status(404).json({
        error: 'Industry not found',
        code: 'INVALID_INPUT',
        available: INDUSTRY_BENCHMARKS.map((b) => b.industry),
      });
    }
  } catch (err: unknown) {
    console.error('industry-benchmarks handler error:', err);
    res.status(500).json({ error: 'Internal server error', code: 'INTERNAL_ERROR' });
  }
}

function getCachedBenchmark(industry: string): IndustryBenchmark | undefined {
  const key = industry.toLowerCase();
  const now = Date.now();
  const cached = benchmarkCache.get(key);
  if (cached && now < cached.expiry) {
    return cached.value;
  }
  const result = lookupBenchmark(industry);
  if (result) {
    benchmarkCache.set(key, { value: result, expiry: now + BENCHMARK_CACHE_TTL_MS });
  }
  return result;
}
