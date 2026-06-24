import type { FinancialData } from '../models/financialTypes';

type FieldKey = keyof FinancialData;

const ALIASES: ReadonlyArray<[RegExp, FieldKey]> = [
  [/^(?:revenue|rev|sales|top\s*line)$/i, 'revenue'],
  [/^(?:operating\s*income|ebit|op\s*income)$/i, 'operatingIncome'],
  [/^(?:tax\s*rate|tax)$/i, 'taxRate'],
  [/^(?:d&a|depreciation\s*&?\s*amortization|depreciation\s*and\s*amortization|depreciation)$/i, 'depreciationAmortization'],
  [/^(?:capex|capital\s*expenditures?|capital\s*expenditure)$/i, 'capitalExpenditures'],
  [/^(?:change\s*in\s*nwc|nwc|change\s*in\s*net\s*working\s*capital)$/i, 'changeInNWC'],
  [/^(?:net\s*debt)$/i, 'netDebt'],
  [/^(?:shares\s*outstanding|shares|diluted\s*shares)$/i, 'sharesOutstanding'],
];

export function matchLabel(label: string): FieldKey | undefined {
  const trimmed = label.trim();
  for (const [regex, field] of ALIASES) {
    if (regex.test(trimmed)) return field;
  }
  return undefined;
}

export function parseNumericValue(raw: string): number | undefined {
  let str = raw.trim().replace(/,/g, '');
  let multiplier = 1;

  const suffixMatch = str.match(/([kmb])$/i);
  if (suffixMatch) {
    const suffix = suffixMatch[1].toUpperCase();
    if (suffix === 'K') multiplier = 1e3;
    else if (suffix === 'M') multiplier = 1e6;
    else if (suffix === 'B') multiplier = 1e9;
    str = str.slice(0, -1);
  }

  const num = Number(str);
  if (isNaN(num)) return undefined;
  return num * multiplier;
}

// Regex: label (separator) value
// Separators: colon, equals, or whitespace before a digit/sign
const LINE_PATTERN = /^(.+?)(?:\s*[:=]\s*|\s+)([-+]?[\d.,]+[kmb]?)$/i;

export function parsePlainText(text: string): { parsed: Partial<FinancialData>; errors: string[] } {
  const parsed: Partial<FinancialData> = {};
  const errors: string[] = [];

  const lines = text.split(/\r?\n/);

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === '') continue;

    const match = trimmed.match(LINE_PATTERN);
    if (!match) {
      errors.push(line.trimEnd());
      continue;
    }

    const [, labelPart, valuePart] = match;
    const field = matchLabel(labelPart);
    if (!field) {
      errors.push(line.trimEnd());
      continue;
    }

    const num = parseNumericValue(valuePart);
    if (num === undefined) {
      errors.push(line.trimEnd());
      continue;
    }

    parsed[field] = num;
  }

  return { parsed, errors };
}
