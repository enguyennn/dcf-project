import type { ParseResponse } from '../models/aiTypes';

/**
 * Calls the server-side AI parse endpoint.
 * This module is a code-split boundary — only reached via dynamic import().
 */
export async function parseWithAI(text: string, industry?: string): Promise<ParseResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10_000);

  try {
    const body: Record<string, string> = { text };
    if (industry !== undefined) {
      body.industry = industry;
    }

    const res = await fetch('/api/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    clearTimeout(timer);

    if (!res.ok) {
      const detail = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      throw new Error(detail.error || `HTTP ${res.status}`);
    }

    const json: ParseResponse = await res.json();
    return json;
  } catch (e: unknown) {
    clearTimeout(timer);
    throw e instanceof Error ? e : new Error('Unknown error');
  }
}
