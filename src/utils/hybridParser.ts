import { parsePlainText } from './parsePlainText';
import type { DCFInputs } from '../models/financialTypes';
import type { AssumptionMetadata, ParseResponse } from '../models/aiTypes';

export interface HybridParseResult {
  parsed: Partial<DCFInputs>;
  metadata: AssumptionMetadata[];
  errors: string[];
}

function buildUserMetadata(parsed: Partial<DCFInputs>): AssumptionMetadata[] {
  return Object.entries(parsed).map(([field, value]) => ({
    field,
    value: value as number,
    source: 'user-provided' as const,
    confidence: 'high' as const,
    rationale: 'Parsed directly from structured input',
  }));
}

function mergeAIIntoResult(
  regexParsed: Partial<DCFInputs>,
  regexMeta: AssumptionMetadata[],
  ai: ParseResponse,
): { parsed: Partial<DCFInputs>; metadata: AssumptionMetadata[] } {
  const parsed: Partial<DCFInputs> = { ...regexParsed };
  const metaByField = new Map<string, AssumptionMetadata>();

  for (const m of regexMeta) {
    metaByField.set(m.field, m);
  }

  for (const [key, val] of Object.entries(ai.assumptions)) {
    if (!(key in parsed)) {
      (parsed as Record<string, unknown>)[key] = val;
    }
  }

  for (const m of ai.metadata) {
    if (!metaByField.has(m.field)) {
      metaByField.set(m.field, m);
    }
  }

  return { parsed, metadata: Array.from(metaByField.values()) };
}

export async function hybridParse(text: string): Promise<HybridParseResult> {
  const regex = parsePlainText(text);
  const regexKeys = Object.keys(regex.parsed);

  // Case 1: all lines matched — pure client-side
  if (regex.errors.length === 0) {
    return { parsed: regex.parsed, metadata: buildUserMetadata(regex.parsed), errors: [] };
  }

  // Case 2 & 3: need AI for unmatched lines (or full text)
  const regexMeta = buildUserMetadata(regex.parsed);
  const aiText = regexKeys.length > 0 ? regex.errors.join('\n') : text;

  try {
    const { parseWithAI } = await import('./aiClient');
    const aiResult = await parseWithAI(aiText);
    const merged = mergeAIIntoResult(regex.parsed, regexMeta, aiResult);
    return { parsed: merged.parsed, metadata: merged.metadata, errors: [] };
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Unknown error';
    return { parsed: regex.parsed, metadata: regexMeta, errors: [msg] };
  }
}
