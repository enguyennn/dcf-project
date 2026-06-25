import type { VercelRequest, VercelResponse } from '@vercel/node';
import { applyCors } from './lib/cors';
import { checkRateLimit } from './lib/rateLimiter';
import { validateParseInput } from './lib/validation';
import { validateLLMOutput } from './lib/plausibilityValidator';
import { OpenAIProvider } from './lib/llmProvider';
import type { LLMProvider } from './lib/llmProvider';
import type { ParseResponse } from '../src/models/aiTypes';

/** Required-field → follow-up question map. */
const REQUIRED_FIELD_QUESTIONS: Record<string, string> = {
  revenue: "What is the company's annual revenue?",
  revenueGrowthRate: 'What is the expected revenue growth rate?',
  operatingMarginRate: 'What is the operating margin?',
};

/**
 * Core parse logic — testable without req/res or network.
 *
 * 1. Validate input
 * 2. Call LLM provider
 * 3. Run plausibility checks / auto-correct
 * 4. Generate follow-up questions for missing fields
 */
export async function handleParse(
  body: unknown,
  provider: LLMProvider,
): Promise<{ status: number; body: ParseResponse | { error: string } }> {
  const input = validateParseInput(body);
  if (!input.valid) {
    return { status: 400, body: { error: input.error } };
  }

  const result = await provider.parseFinancialText(input.text, input.industry);

  const { valid, corrections } = validateLLMOutput(result.assumptions);

  // Append correction notes to matching metadata entries
  const metadata = result.metadata.map((m) => {
    const correction = corrections[m.field];
    if (correction) {
      return {
        ...m,
        value: correction.to,
        rationale: `${m.rationale} (auto-corrected from ${correction.from} to ${correction.to})`,
      };
    }
    return m;
  });

  // Determine if any numeric financial fields were extracted
  const hasFinancialFields =
    Object.keys(valid).length > 0 && Object.keys(valid).some((k) => k !== 'company');

  // Compute follow-up questions
  const followUp: string[] = [];

  if (!hasFinancialFields) {
    // Zero extraction — return all follow-up questions
    for (const question of Object.values(REQUIRED_FIELD_QUESTIONS)) {
      followUp.push(question);
    }
    return { status: 200, body: { assumptions: {}, metadata: [], followUp } };
  }

  // Check for missing required fields
  for (const [field, question] of Object.entries(REQUIRED_FIELD_QUESTIONS)) {
    if ((valid as Record<string, unknown>)[field] === undefined) {
      followUp.push(question);
    }
  }

  return {
    status: 200,
    body: {
      assumptions: valid,
      metadata,
      ...(followUp.length > 0 ? { followUp } : {}),
    },
  };
}

export default async function handler(req: VercelRequest, res: VercelResponse): Promise<void> {
  if (applyCors(req, res)) return;

  if (req.method !== 'POST') {
    res.status(405).json({ error: 'Method not allowed' });
    return;
  }

  const forwarded = req.headers['x-forwarded-for'];
  const ip = typeof forwarded === 'string' ? forwarded.split(',')[0].trim() : 'unknown';

  const { allowed } = checkRateLimit(ip);
  if (!allowed) {
    res.status(429).json({ error: 'Too many requests' });
    return;
  }

  const { status, body } = await handleParse(req.body, new OpenAIProvider());
  res.status(status).json(body);
}
