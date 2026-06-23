import { describe, it, expect } from 'vitest';
import { DEFAULT_ASSUMPTIONS } from '../src/data/defaultAssumptions';
import type {
  FinancialData,
  WACCInputs,
  TerminalValueInputs,
  ProjectionInputs,
  CompanyInfo,
  DCFInputs,
  DCFOutputs,
  ValidationWarning,
  AssumptionDefaults,
} from '../src/models/financialTypes';

describe('DEFAULT_ASSUMPTIONS', () => {
  it('has correct riskFreeRate', () => {
    expect(DEFAULT_ASSUMPTIONS.riskFreeRate).toBe(0.04);
  });

  it('has correct beta', () => {
    expect(DEFAULT_ASSUMPTIONS.beta).toBe(1.0);
  });

  it('has correct equityRiskPremium', () => {
    expect(DEFAULT_ASSUMPTIONS.equityRiskPremium).toBe(0.055);
  });

  it('has correct costOfDebt', () => {
    expect(DEFAULT_ASSUMPTIONS.costOfDebt).toBe(0.05);
  });

  it('has correct debtToEquityRatio', () => {
    expect(DEFAULT_ASSUMPTIONS.debtToEquityRatio).toBe(0.5);
  });

  it('has correct taxRate', () => {
    expect(DEFAULT_ASSUMPTIONS.taxRate).toBe(0.21);
  });

  it('has correct perpetuityGrowthRate', () => {
    expect(DEFAULT_ASSUMPTIONS.perpetuityGrowthRate).toBe(0.025);
  });

  it('has correct exitMultiple', () => {
    expect(DEFAULT_ASSUMPTIONS.exitMultiple).toBe(10);
  });

  it('has correct revenueGrowthRate', () => {
    expect(DEFAULT_ASSUMPTIONS.revenueGrowthRate).toBe(0.05);
  });

  it('has correct operatingMarginRate', () => {
    expect(DEFAULT_ASSUMPTIONS.operatingMarginRate).toBe(0.15);
  });

  it('has correct dAndARate', () => {
    expect(DEFAULT_ASSUMPTIONS.dAndARate).toBe(0.03);
  });

  it('has correct capExRate', () => {
    expect(DEFAULT_ASSUMPTIONS.capExRate).toBe(0.04);
  });

  it('has correct nwcRate', () => {
    expect(DEFAULT_ASSUMPTIONS.nwcRate).toBe(0.01);
  });

  it('has correct projectionYears', () => {
    expect(DEFAULT_ASSUMPTIONS.projectionYears).toBe(5);
  });

  it('is assignable to AssumptionDefaults type', () => {
    const typed: AssumptionDefaults = DEFAULT_ASSUMPTIONS;
    expect(typed).toBeDefined();
  });
});

// Compile-time type conformance checks (these verify the types exist and compile)
describe('Type conformance', () => {
  it('FinancialData interface has expected shape', () => {
    const data: FinancialData = {
      revenue: 0,
      operatingIncome: 0,
      taxRate: 0,
      depreciationAmortization: 0,
      capitalExpenditures: 0,
      changeInNWC: 0,
      netDebt: 0,
      sharesOutstanding: 0,
    };
    expect(data).toBeDefined();
  });

  it('WACCInputs interface has expected shape', () => {
    const inputs: WACCInputs = {
      riskFreeRate: 0,
      beta: 0,
      equityRiskPremium: 0,
      costOfDebt: 0,
      debtToEquityRatio: 0,
    };
    expect(inputs).toBeDefined();
  });

  it('TerminalValueInputs interface has expected shape', () => {
    const inputs: TerminalValueInputs = {
      perpetuityGrowthRate: 0,
      exitMultiple: 0,
      finalYearEBITDA: 0,
      method: 'perpetuity',
    };
    expect(inputs).toBeDefined();
  });

  it('ProjectionInputs interface has expected shape', () => {
    const inputs: ProjectionInputs = {
      revenueGrowthRate: 0,
      operatingMarginRate: 0,
      dAndARate: 0,
      capExRate: 0,
      nwcRate: 0,
      projectionYears: 0,
    };
    expect(inputs).toBeDefined();
  });

  it('CompanyInfo interface has expected shape', () => {
    const info: CompanyInfo = {
      companyName: 'Test',
      currency: 'USD',
    };
    expect(info).toBeDefined();
  });

  it('DCFInputs combines all interfaces', () => {
    const inputs: DCFInputs = {
      revenue: 0,
      operatingIncome: 0,
      taxRate: 0,
      depreciationAmortization: 0,
      capitalExpenditures: 0,
      changeInNWC: 0,
      netDebt: 0,
      sharesOutstanding: 0,
      riskFreeRate: 0,
      beta: 0,
      equityRiskPremium: 0,
      costOfDebt: 0,
      debtToEquityRatio: 0,
      perpetuityGrowthRate: 0,
      exitMultiple: 0,
      finalYearEBITDA: 0,
      method: 'perpetuity',
      revenueGrowthRate: 0,
      operatingMarginRate: 0,
      dAndARate: 0,
      capExRate: 0,
      nwcRate: 0,
      projectionYears: 0,
      company: { companyName: 'Test', currency: 'USD' },
    };
    expect(inputs).toBeDefined();
  });

  it('DCFOutputs interface has expected shape', () => {
    const outputs: DCFOutputs = {
      projectedRevenue: [],
      projectedFCFF: [],
      discountFactors: [],
      pvFCFF: [],
      terminalValue: 0,
      pvTerminalValue: 0,
      enterpriseValue: 0,
      equityValue: 0,
      impliedSharePrice: 0,
      wacc: 0,
    };
    expect(outputs).toBeDefined();
  });

  it('ValidationWarning interface has expected shape', () => {
    const warning: ValidationWarning = {
      field: 'test',
      message: 'test',
      severity: 'warning',
    };
    expect(warning).toBeDefined();
  });
});
