import type { VercelRequest, VercelResponse } from '@vercel/node';
import { applyCors } from '../lib/cors';
import { checkRateLimit } from '../lib/rateLimiter';

export default function handler(req: VercelRequest, res: VercelResponse): void {
  if (applyCors(req, res)) return;

  if (req.method !== 'GET') {
    res.status(405).json({ error: 'Method not allowed', code: 'METHOD_NOT_ALLOWED' });
    return;
  }

  const forwarded = req.headers['x-forwarded-for'];
  const ip = typeof forwarded === 'string' ? forwarded.split(',')[0].trim() : 'unknown';

  const { allowed, retryAfterSeconds } = checkRateLimit(`health:${ip}`, 60);
  if (!allowed) {
    res.setHeader('Retry-After', String(retryAfterSeconds));
    res.status(429).json({ error: 'Rate limit exceeded', code: 'RATE_LIMITED' });
    return;
  }

  res.status(200).json({ status: 'ok', timestamp: new Date().toISOString() });
}
