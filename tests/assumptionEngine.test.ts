import { describe, it, expect } from 'vitest';
import { mergeAssumptions, createScenario } from '../src/utils/assumptionEngine';
import { DEFAULT_ASSUMPTIONS } from '../src/data/defaultAssumptions';
import type { DCFInputs } from '../src/models/financialTypes';

describe('mergeAssumptions', () => {
  it('returns complete DCFInputs with all defaults when given empty input', () => {
    const result = mergeAssumptions({});
    expect(result.revenue).toBe(0);
    expect(result.riskFreeRate).toBe(DEFAULT_ASSUMPTIONS.riskFreeRate);
    expect(result.projectionYears).toBe(DEFAULT_ASSUMPTIONS.projectionYears);
    expect(result.method).toBe('perpetuity');
    expect(result.company).toEqual({ companyName: '', currency: 'USD' });
  });

  it('user override wins over defaults', () => {
    const result = mergeAssumptions({ revenue: 5000000, riskFreeRate: 0.03 });
    expect(result.revenue).toBe(5000000);
    expect(result.riskFreeRate).toBe(0.03);
    // Other defaults preserved
    expect(result.beta).toBe(DEFAULT_ASSUMPTIONS.beta);
  });

  it('merges company fields without losing base company defaults', () => {
    const result = mergeAssumptions({ company: { companyName: 'Acme', currency: 'EUR' } });
    expect(result.company.companyName).toBe('Acme');
    expect(result.company.currency).toBe('EUR');
  });

  it('returned object satisfies all DCFInputs keys', () => {
    const result = mergeAssumptions({});
    const requiredKeys: (keyof DCFInputs)[] = [
      'revenue', 'operatingIncome', 'taxRate', 'depreciationAmortization',
      'capitalExpenditures', 'changeInNWC', 'netDebt', 'sharesOutstanding',
      'riskFreeRate', 'beta', 'equityRiskPremium', 'costOfDebt', 'debtToEquityRatio',
      'perpetuityGrowthRate', 'exitMultiple', 'finalYearEBITDA', 'method',
      'revenueGrowthRate', 'operatingMarginRate', 'dAndARate', 'capExRate',
      'nwcRate', 'projectionYears', 'company',
    ];
    for (const key of requiredKeys) {
      expect(result).toHaveProperty(key);
    }
  });
});

describe('createScenario', () => {
  const base: DCFInputs = mergeAssumptions({ revenue: 1000000, revenueGrowthRate: 0.05, riskFreeRate: 0.04 });

  it('base scenario returns equivalent object without mutation', () => {
    const result = createScenario(base, 'base');
    expect(result).toEqual(base);
    expect(result).not.toBe(base);
    expect(result.company).not.toBe(base.company);
  });

  it('conservative lowers growth by 2% and raises riskFreeRate by 1%', () => {
    const result = createScenario(base, 'conservative');
    expect(result.revenueGrowthRate).toBeCloseTo(0.03);
    expect(result.riskFreeRate).toBeCloseTo(0.05);
  });

  it('optimistic raises growth by 2% and lowers riskFreeRate by 1%', () => {
    const result = createScenario(base, 'optimistic');
    expect(result.revenueGrowthRate).toBeCloseTo(0.07);
    expect(result.riskFreeRate).toBeCloseTo(0.03);
  });

  it('does not mutate the base object', () => {
    const original = { ...base, company: { ...base.company } };
    createScenario(base, 'conservative');
    createScenario(base, 'optimistic');
    expect(base).toEqual(original);
  });
});
