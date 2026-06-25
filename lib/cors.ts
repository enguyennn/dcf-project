import type { VercelRequest, VercelResponse } from '@vercel/node';

export function applyCors(req: VercelRequest, res: VercelResponse): boolean {
  const allowedOrigin = process.env.ALLOWED_ORIGIN || '*';
  const requestOrigin = req.headers.origin as string | undefined;

  // When a specific origin is configured, enforce it
  if (allowedOrigin !== '*' && requestOrigin && requestOrigin !== allowedOrigin) {
    res.status(403).json({ error: 'Origin not allowed', code: 'FORBIDDEN_ORIGIN' });
    return true;
  }

  res.setHeader('Access-Control-Allow-Origin', allowedOrigin);
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.status(204).end();
    return true;
  }

  return false;
}
