import { describe, it, expect } from 'vitest';
import { INDUSTRY_BENCHMARKS, lookupBenchmark } from '../src/data/industryBenchmarks';

describe('INDUSTRY_BENCHMARKS dataset', () => {
  it('contains at least 10 industries', () => {
    expect(INDUSTRY_BENCHMARKS.length).toBeGreaterThanOrEqual(10);
  });

  it('all six rate fields are finite decimals in [0, 1]', () => {
    const rateFields = [
      'revenueGrowthRate',
      'operatingMarginRate',
      'dAndARate',
      'capExRate',
      'nwcRate',
      'costOfDebt',
    ] as const;

    for (const entry of INDUSTRY_BENCHMARKS) {
      for (const field of rateFields) {
        const value = entry[field];
        expect(value, `${entry.industry}.${field}`).toBeTypeOf('number');
        expect(Number.isFinite(value), `${entry.industry}.${field} finite`).toBe(true);
        expect(value, `${entry.industry}.${field} >= 0`).toBeGreaterThanOrEqual(0);
        expect(value, `${entry.industry}.${field} <= 1`).toBeLessThanOrEqual(1);
      }
    }
  });

  it('betaRange values are finite numbers (not constrained to [0,1])', () => {
    for (const entry of INDUSTRY_BENCHMARKS) {
      expect(Number.isFinite(entry.betaRange.low), `${entry.industry}.betaRange.low`).toBe(true);
      expect(Number.isFinite(entry.betaRange.mid), `${entry.industry}.betaRange.mid`).toBe(true);
      expect(Number.isFinite(entry.betaRange.high), `${entry.industry}.betaRange.high`).toBe(true);
      expect(entry.betaRange.low).toBeLessThanOrEqual(entry.betaRange.mid);
      expect(entry.betaRange.mid).toBeLessThanOrEqual(entry.betaRange.high);
    }
  });
});

describe('lookupBenchmark', () => {
  it('matches exact industry name case-insensitively', () => {
    const result = lookupBenchmark('SaaS');
    expect(result).toBeDefined();
    expect(result!.industry).toBe('SaaS');

    const lower = lookupBenchmark('saas');
    expect(lower).toBeDefined();
    expect(lower!.industry).toBe('SaaS');
  });

  it('matches aliases case-insensitively', () => {
    const result = lookupBenchmark('software');
    expect(result).toBeDefined();
    expect(result!.industry).toBe('SaaS');

    const fintech = lookupBenchmark('financial technology');
    expect(fintech).toBeDefined();
    expect(fintech!.industry).toBe('Fintech');

    const payments = lookupBenchmark('Payments');
    expect(payments).toBeDefined();
    expect(payments!.industry).toBe('Fintech');
  });

  it('matches via substring containment', () => {
    const result = lookupBenchmark('cloud software');
    expect(result).toBeDefined();
    expect(result!.industry).toBe('SaaS');
  });

  it('returns undefined for unknown industry', () => {
    expect(lookupBenchmark('zzz-nonexistent')).toBeUndefined();
  });

  it('returns undefined for empty string', () => {
    expect(lookupBenchmark('')).toBeUndefined();
  });

  it('returns undefined for whitespace-only input', () => {
    expect(lookupBenchmark('   ')).toBeUndefined();
    expect(lookupBenchmark('\t\n')).toBeUndefined();
  });
});
