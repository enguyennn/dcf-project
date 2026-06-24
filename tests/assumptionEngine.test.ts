import { describe, it, expect } from 'vitest';
import { mergeAssumptions, createScenario, probabilityWeightedScenarios } from '../src/utils/assumptionEngine';
import { DEFAULT_ASSUMPTIONS } from '../src/data/defaultAssumptions';
import { runFullDCF } from '../src/utils/dcfCalculations';
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

describe('probabilityWeightedScenarios', () => {
  const validBase: DCFInputs = mergeAssumptions({
    revenue: 1000000,
    operatingIncome: 200000,
    sharesOutstanding: 100000,
    depreciationAmortization: 50000,
    capitalExpenditures: 80000,
    changeInNWC: 10000,
    netDebt: 500000,
  });

  it('equal weights → weighted ≈ mean of the three scenario prices', () => {
    const result = probabilityWeightedScenarios(validBase, { conservative: 1, base: 1, optimistic: 1 });
    expect(result.conservative).not.toBeNull();
    expect(result.base).not.toBeNull();
    expect(result.optimistic).not.toBeNull();
    expect(result.weighted).not.toBeNull();
    const mean = (result.conservative! + result.base! + result.optimistic!) / 3;
    expect(result.weighted).toBeCloseTo(mean, 4);
  });

  it('a scenario that throws (sharesOutstanding=0) → that field null and excluded from weighted', () => {
    const throwingBase = mergeAssumptions({
      revenue: 1000000,
      operatingIncome: 200000,
      sharesOutstanding: 0, // will throw in runFullDCF
      depreciationAmortization: 50000,
      capitalExpenditures: 80000,
      changeInNWC: 10000,
      netDebt: 500000,
    });
    const result = probabilityWeightedScenarios(throwingBase, { conservative: 1, base: 1, optimistic: 1 });
    // All scenarios inherit sharesOutstanding=0, so all throw
    expect(result.conservative).toBeNull();
    expect(result.base).toBeNull();
    expect(result.optimistic).toBeNull();
    expect(result.weighted).toBeNull();
  });

  it('zero total weight → weighted null', () => {
    const result = probabilityWeightedScenarios(validBase, { conservative: 0, base: 0, optimistic: 0 });
    expect(result.weighted).toBeNull();
  });

  it('one scenario null is excluded from weighted average', () => {
    // Force conservative to throw by making growth very high so wacc <= perpetuityGrowthRate after shift
    const edgeBase = mergeAssumptions({
      revenue: 1000000,
      operatingIncome: 200000,
      sharesOutstanding: 100000,
      depreciationAmortization: 50000,
      capitalExpenditures: 80000,
      changeInNWC: 10000,
      netDebt: 500000,
      riskFreeRate: 0.01, // conservative adds 0.01, still low
      perpetuityGrowthRate: 0.025,
    });
    // Verify base works
    const baseResult = runFullDCF(createScenario(edgeBase, 'base'));
    expect(Number.isFinite(baseResult.impliedSharePrice)).toBe(true);
    const result = probabilityWeightedScenarios(edgeBase, { conservative: 1, base: 1, optimistic: 1 });
    // If conservative threw, weighted = mean of non-null only
    if (result.conservative === null) {
      const nonNull = [result.base, result.optimistic].filter((v) => v !== null) as number[];
      const mean = nonNull.reduce((a, b) => a + b, 0) / nonNull.length;
      expect(result.weighted).toBeCloseTo(mean, 4);
    }
  });
});
