import type { DCFInputs } from '../src/models/financialTypes';

/** Rate fields eligible for auto-correction (percentage → decimal). */
const RATE_FIELDS: ReadonlyArray<keyof DCFInputs> = [
  'revenueGrowthRate',
  'operatingMarginRate',
  'dAndARate',
  'capExRate',
  'nwcRate',
  'taxRate',
  'costOfDebt',
];

/** Acceptable ranges per field. Outliers are flagged, not rejected. */
const RANGE_LIMITS: Partial<Record<keyof DCFInputs, [number, number]>> = {
  revenueGrowthRate: [-0.5, 1.0],
  operatingMarginRate: [-0.5, 0.9],
  dAndARate: [0, 1],
  capExRate: [0, 1],
  nwcRate: [0, 1],
  taxRate: [0, 1],
  costOfDebt: [0, 1],
  beta: [0, 5],
};

/**
 * Validate and auto-correct LLM-extracted assumptions.
 *
 * - Rates >1 and <100 are auto-divided by 100 (assumed percentage).
 * - Out-of-range values are warned but kept.
 */
export function validateLLMOutput(parsed: Partial<DCFInputs>): {
  valid: Partial<DCFInputs>;
  warnings: string[];
  corrections: Record<string, { from: number; to: number }>;
} {
  // Shallow copy; deep-copy company if present
  const valid: Partial<DCFInputs> = { ...parsed };
  if (parsed.company) {
    valid.company = { ...parsed.company };
  }

  const warnings: string[] = [];
  const corrections: Record<string, { from: number; to: number }> = {};

  // Auto-divide rates that look like whole-number percentages
  for (const field of RATE_FIELDS) {
    const val = valid[field];
    if (typeof val === 'number' && val > 1 && val < 100) {
      const corrected = val / 100;
      corrections[field] = { from: val, to: corrected };
      warnings.push(`${field}: auto-corrected from ${val} to ${corrected} (assumed percentage)`);
      (valid as Record<string, unknown>)[field] = corrected;
    }
  }

  // Range checks — flag but keep
  for (const [field, range] of Object.entries(RANGE_LIMITS)) {
    const val = valid[field as keyof DCFInputs];
    if (typeof val === 'number') {
      const [min, max] = range;
      if (val < min || val > max) {
        warnings.push(`${field}: value ${val} is outside expected range [${min}, ${max}]`);
      }
    }
  }

  // Revenue positivity
  if (typeof valid.revenue === 'number' && valid.revenue <= 0) {
    warnings.push(`revenue: value ${valid.revenue} should be positive`);
  }

  return { valid, warnings, corrections };
}
