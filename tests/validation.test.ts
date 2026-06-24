import { describe, it, expect } from 'vitest';
import { validateInputs, validateOutputs } from '../src/utils/validation';
import type { DCFInputs, DCFOutputs } from '../src/models/financialTypes';

/** Base valid fixture — triggers zero warnings */
const validInputs: DCFInputs = {
  // FinancialData
  revenue: 1_000_000,
  operatingIncome: 200_000,
  taxRate: 0.21,
  depreciationAmortization: 50_000,
  capitalExpenditures: 80_000,
  changeInNWC: 10_000,
  netDebt: 500_000,
  sharesOutstanding: 100_000,
  // WACCInputs
  riskFreeRate: 0.04,
  beta: 1.2,
  equityRiskPremium: 0.055,
  costOfDebt: 0.05,
  debtToEquityRatio: 0.5,
  // TerminalValueInputs
  perpetuityGrowthRate: 0.025,
  exitMultiple: 10,
  finalYearEBITDA: 300_000,
  method: 'perpetuity',
  // ProjectionInputs
  revenueGrowthRate: 0.10,
  operatingMarginRate: 0.20,
  dAndARate: 0.03,
  capExRate: 0.04,
  nwcRate: 0.05,
  projectionYears: 5,
  // CompanyInfo
  company: {
    companyName: 'TestCo',
    tickerSymbol: 'TST',
    industry: 'technology',
    currency: 'USD',
  },
};

/** Base valid outputs fixture — terminal value is small relative to EV */
const validOutputs: DCFOutputs = {
  projectedRevenue: [1_100_000, 1_210_000],
  projectedFCFF: [150_000, 165_000],
  discountFactors: [0.92, 0.85],
  pvFCFF: [138_000, 140_250],
  terminalValue: 2_000_000,
  pvTerminalValue: 1_700_000,
  enterpriseValue: 5_000_000,
  equityValue: 4_500_000,
  impliedSharePrice: 45,
  wacc: 0.084,
};

describe('validateInputs', () => {
  it('returns zero warnings for valid inputs', () => {
    const warnings = validateInputs(validInputs);
    expect(warnings).toEqual([]);
  });

  // Rule 1: WACC ≤ perpetuityGrowthRate → error
  it('returns error when WACC ≤ perpetuityGrowthRate', () => {
    const inputs: DCFInputs = {
      ...validInputs,
      perpetuityGrowthRate: 0.15, // higher than WACC (~0.084)
    };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'perpetuityGrowthRate' && w.severity === 'error')).toBe(true);
  });

  it('returns error when perpetuityGrowthRate equals WACC', () => {
    // WACC for these inputs ≈ 0.08389
    const inputs: DCFInputs = {
      ...validInputs,
      perpetuityGrowthRate: 0.084,
    };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'perpetuityGrowthRate' && w.severity === 'error')).toBe(true);
  });

  // Rule 2: revenueGrowthRate > 0.30 or < -0.20 → warning
  it('warns when revenueGrowthRate > 0.30', () => {
    const inputs: DCFInputs = { ...validInputs, revenueGrowthRate: 0.35 };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'revenueGrowthRate' && w.severity === 'warning')).toBe(true);
  });

  it('warns when revenueGrowthRate < -0.20', () => {
    const inputs: DCFInputs = { ...validInputs, revenueGrowthRate: -0.25 };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'revenueGrowthRate' && w.severity === 'warning')).toBe(true);
  });

  it('does not warn when revenueGrowthRate is within bounds', () => {
    const inputs: DCFInputs = { ...validInputs, revenueGrowthRate: 0.15 };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'revenueGrowthRate')).toBe(false);
  });

  // Rule 3: operatingMarginRate > 0.50 or < -0.10 → warning
  it('warns when operatingMarginRate > 0.50', () => {
    const inputs: DCFInputs = { ...validInputs, operatingMarginRate: 0.55 };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'operatingMarginRate' && w.severity === 'warning')).toBe(true);
  });

  it('warns when operatingMarginRate < -0.10', () => {
    const inputs: DCFInputs = { ...validInputs, operatingMarginRate: -0.15 };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'operatingMarginRate' && w.severity === 'warning')).toBe(true);
  });

  // Rule 4: capExRate === 0 when revenueGrowthRate > 0 → warning
  it('warns when capExRate is 0 with positive revenueGrowthRate', () => {
    const inputs: DCFInputs = { ...validInputs, capExRate: 0, revenueGrowthRate: 0.10 };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'capExRate' && w.severity === 'warning')).toBe(true);
  });

  it('does not warn when capExRate is 0 with non-positive revenueGrowthRate', () => {
    const inputs: DCFInputs = { ...validInputs, capExRate: 0, revenueGrowthRate: 0 };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'capExRate')).toBe(false);
  });

  // Rule 6: industry is banking/insurance/real-estate → warning
  it('warns when industry is banking (case-insensitive)', () => {
    const inputs: DCFInputs = {
      ...validInputs,
      company: { ...validInputs.company, industry: 'Banking' },
    };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'company.industry' && w.severity === 'warning')).toBe(true);
  });

  it('warns when industry is insurance', () => {
    const inputs: DCFInputs = {
      ...validInputs,
      company: { ...validInputs.company, industry: 'INSURANCE' },
    };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'company.industry' && w.severity === 'warning')).toBe(true);
  });

  it('warns when industry is real-estate', () => {
    const inputs: DCFInputs = {
      ...validInputs,
      company: { ...validInputs.company, industry: 'Real-Estate' },
    };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'company.industry' && w.severity === 'warning')).toBe(true);
  });

  // Rule 7: required numeric field is NaN → error
  it('returns error when a required numeric field is NaN', () => {
    const inputs: DCFInputs = { ...validInputs, revenue: NaN };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'revenue' && w.severity === 'error')).toBe(true);
  });

  it('returns error when a required numeric field is undefined-coerced', () => {
    const inputs: DCFInputs = { ...validInputs, beta: undefined as unknown as number };
    const warnings = validateInputs(inputs);
    expect(warnings.some(w => w.field === 'beta' && w.severity === 'error')).toBe(true);
  });

  // Multiple simultaneous warnings
  it('returns multiple warnings when multiple rules are violated', () => {
    const inputs: DCFInputs = {
      ...validInputs,
      revenueGrowthRate: 0.50,       // rule 2
      operatingMarginRate: 0.60,     // rule 3
      capExRate: 0,                   // rule 4 (growth > 0)
      company: { ...validInputs.company, industry: 'banking' }, // rule 6
    };
    const warnings = validateInputs(inputs);
    expect(warnings.length).toBeGreaterThanOrEqual(4);
    expect(warnings.filter(w => w.severity === 'warning').length).toBeGreaterThanOrEqual(4);
  });

  // Error vs warning distinction
  it('distinguishes error severity from warning severity', () => {
    const inputs: DCFInputs = {
      ...validInputs,
      perpetuityGrowthRate: 0.15,   // rule 1 → error
      revenueGrowthRate: 0.50,       // rule 2 → warning
    };
    const warnings = validateInputs(inputs);
    const errors = warnings.filter(w => w.severity === 'error');
    const warns = warnings.filter(w => w.severity === 'warning');
    expect(errors.length).toBeGreaterThanOrEqual(1);
    expect(warns.length).toBeGreaterThanOrEqual(1);
  });
});

describe('validateOutputs', () => {
  // Rule 5: terminalValue > 0.85 * enterpriseValue → warning
  it('returns zero warnings for valid outputs', () => {
    const warnings = validateOutputs(validOutputs);
    expect(warnings).toEqual([]);
  });

  it('warns when terminalValue dominates enterpriseValue', () => {
    const outputs: DCFOutputs = {
      ...validOutputs,
      terminalValue: 9_000_000,
      enterpriseValue: 10_000_000, // TV is 90% of EV
    };
    const warnings = validateOutputs(outputs);
    expect(warnings.some(w => w.field === 'terminalValue' && w.severity === 'warning')).toBe(true);
  });

  it('does not warn when terminalValue is exactly 85% of enterpriseValue', () => {
    const outputs: DCFOutputs = {
      ...validOutputs,
      terminalValue: 8_500_000,
      enterpriseValue: 10_000_000,
    };
    const warnings = validateOutputs(outputs);
    expect(warnings.some(w => w.field === 'terminalValue')).toBe(false);
  });
});
