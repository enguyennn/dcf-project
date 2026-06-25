const requests = new Map<string, number[]>();

export function checkRateLimit(
  ip: string,
  limit = 20,
  windowMs = 60_000
): { allowed: boolean; remaining: number } {
  const now = Date.now();
  const timestamps = requests.get(ip) ?? [];

  // Prune entries older than the window
  const valid = timestamps.filter((t) => now - t < windowMs);

  if (valid.length >= limit) {
    requests.set(ip, valid);
    return { allowed: false, remaining: 0 };
  }

  valid.push(now);
  requests.set(ip, valid);

  return { allowed: true, remaining: Math.max(0, limit - valid.length) };
}

/** Test helper — clears the in-memory store so tests are isolated. */
export function __resetRateLimiter(): void {
  requests.clear();
}
