import type { VercelRequest, VercelResponse } from '@vercel/node';
import { applyCors } from './lib/cors';
import { checkRateLimit } from './lib/rateLimiter';
import { INDUSTRY_BENCHMARKS, lookupBenchmark } from '../src/data/industryBenchmarks';

export default function handler(req: VercelRequest, res: VercelResponse) {
  if (applyCors(req, res)) return;

  if (req.method !== 'GET') {
    res.status(405).json({ error: 'Method not allowed' });
    return;
  }

  const forwarded = req.headers['x-forwarded-for'];
  const ip = typeof forwarded === 'string'
    ? forwarded.split(',')[0].trim()
    : 'unknown';

  const { allowed } = checkRateLimit(ip);
  if (!allowed) {
    res.status(429).json({ error: 'Rate limit exceeded' });
    return;
  }

  const rawIndustry = req.query.industry;
  const industry = Array.isArray(rawIndustry) ? rawIndustry[0] : rawIndustry;

  const benchmark = industry ? lookupBenchmark(industry) : undefined;

  if (benchmark) {
    res.status(200).json(benchmark);
  } else {
    res.status(404).json({
      error: 'Industry not found',
      available: INDUSTRY_BENCHMARKS.map((b) => b.industry),
    });
  }
}
