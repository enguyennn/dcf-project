import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { applyCors } from '../lib/cors';
import type { VercelRequest, VercelResponse } from '@vercel/node';

function mockReq(method: string, origin?: string): VercelRequest {
  return {
    method,
    headers: origin ? { origin } : {},
  } as unknown as VercelRequest;
}

function mockRes() {
  const res = {
    setHeader: vi.fn().mockReturnThis(),
    status: vi.fn().mockReturnThis(),
    json: vi.fn().mockReturnThis(),
    end: vi.fn().mockReturnThis(),
  };
  return res as unknown as VercelResponse & typeof res;
}

describe('applyCors', () => {
  beforeEach(() => {
    vi.stubEnv('ALLOWED_ORIGIN', '');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('allows all origins when ALLOWED_ORIGIN is unset', () => {
    const req = mockReq('GET', 'https://evil.com');
    const res = mockRes();
    const handled = applyCors(req, res);
    expect(handled).toBe(false);
    expect(res.setHeader).toHaveBeenCalledWith('Access-Control-Allow-Origin', '*');
  });

  it('allows all origins when ALLOWED_ORIGIN is "*"', () => {
    vi.stubEnv('ALLOWED_ORIGIN', '*');
    const req = mockReq('GET', 'https://evil.com');
    const res = mockRes();
    const handled = applyCors(req, res);
    expect(handled).toBe(false);
  });

  it('allows matching origin when ALLOWED_ORIGIN is configured', () => {
    vi.stubEnv('ALLOWED_ORIGIN', 'https://myapp.com');
    const req = mockReq('GET', 'https://myapp.com');
    const res = mockRes();
    const handled = applyCors(req, res);
    expect(handled).toBe(false);
    expect(res.setHeader).toHaveBeenCalledWith('Access-Control-Allow-Origin', 'https://myapp.com');
  });

  it('rejects mismatched origin with 403 when ALLOWED_ORIGIN is configured', () => {
    vi.stubEnv('ALLOWED_ORIGIN', 'https://myapp.com');
    const req = mockReq('GET', 'https://evil.com');
    const res = mockRes();
    const handled = applyCors(req, res);
    expect(handled).toBe(true);
    expect(res.status).toHaveBeenCalledWith(403);
    expect(res.json).toHaveBeenCalledWith({ error: 'Origin not allowed', code: 'FORBIDDEN_ORIGIN' });
  });

  it('handles OPTIONS preflight with 204', () => {
    const req = mockReq('OPTIONS', 'https://myapp.com');
    const res = mockRes();
    vi.stubEnv('ALLOWED_ORIGIN', 'https://myapp.com');
    const handled = applyCors(req, res);
    expect(handled).toBe(true);
    expect(res.status).toHaveBeenCalledWith(204);
    expect(res.end).toHaveBeenCalled();
  });

  it('rejects OPTIONS preflight from disallowed origin with 403', () => {
    vi.stubEnv('ALLOWED_ORIGIN', 'https://myapp.com');
    const req = mockReq('OPTIONS', 'https://evil.com');
    const res = mockRes();
    const handled = applyCors(req, res);
    expect(handled).toBe(true);
    expect(res.status).toHaveBeenCalledWith(403);
  });
});
