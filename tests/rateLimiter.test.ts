import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { checkRateLimit, __resetRateLimiter } from '../api/lib/rateLimiter';

describe('checkRateLimit', () => {
  beforeEach(() => {
    __resetRateLimiter();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('allows requests up to the limit', () => {
    const limit = 5;
    for (let i = 0; i < limit; i++) {
      const result = checkRateLimit('192.168.1.1', limit);
      expect(result.allowed).toBe(true);
    }
  });

  it('blocks requests exceeding the limit', () => {
    const limit = 3;
    for (let i = 0; i < limit; i++) {
      checkRateLimit('10.0.0.1', limit);
    }
    const result = checkRateLimit('10.0.0.1', limit);
    expect(result.allowed).toBe(false);
  });

  it('counts remaining correctly', () => {
    const limit = 5;
    const r1 = checkRateLimit('10.0.0.2', limit);
    expect(r1.remaining).toBe(4);

    const r2 = checkRateLimit('10.0.0.2', limit);
    expect(r2.remaining).toBe(3);
  });

  it('remaining is 0 when blocked', () => {
    const limit = 2;
    checkRateLimit('10.0.0.3', limit);
    checkRateLimit('10.0.0.3', limit);
    const result = checkRateLimit('10.0.0.3', limit);
    expect(result.allowed).toBe(false);
    expect(result.remaining).toBe(0);
  });

  it('isolates different IPs', () => {
    const limit = 1;
    checkRateLimit('ip-a', limit);
    const result = checkRateLimit('ip-b', limit);
    expect(result.allowed).toBe(true);
  });

  it('allows requests again after the window expires', () => {
    const limit = 2;
    const windowMs = 1000;

    checkRateLimit('10.0.0.4', limit, windowMs);
    checkRateLimit('10.0.0.4', limit, windowMs);

    // Blocked now
    expect(checkRateLimit('10.0.0.4', limit, windowMs).allowed).toBe(false);

    // Advance time past the window
    vi.advanceTimersByTime(1001);

    // Should be allowed again
    const result = checkRateLimit('10.0.0.4', limit, windowMs);
    expect(result.allowed).toBe(true);
    expect(result.remaining).toBe(1);
  });

  it('uses default limit of 20', () => {
    for (let i = 0; i < 20; i++) {
      expect(checkRateLimit('default-ip').allowed).toBe(true);
    }
    expect(checkRateLimit('default-ip').allowed).toBe(false);
  });
});
