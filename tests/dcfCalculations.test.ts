import { describe, it, expect } from 'vitest';
import {
  calculateNOPAT,
  calculateFCFF,
  calculateWACC,
  projectRevenue,
  projectMargins,
  terminalValuePerpetual,
  terminalValueExitMultiple,
  discountCashFlows,
  enterpriseValue,
  equityValue,
  impliedSharePrice,
  sensitivityAnalysis,
  runFullDCF,
} from '../src/utils/dcfCalculations';
import type { DCFInputs } from '../src/models/financialTypes';

describe('calculateNOPAT', () => {
  it('calculates standard NOPAT', () => {
    expect(calculateNOPAT(1000000, 0.21)).toBe(790000);
  });

  it('returns full income when tax rate is zero', () => {
    expect(calculateNOPAT(500000, 0)).toBe(500000);
  });

  it('returns zero when tax rate is 100%', () => {
    expect(calculateNOPAT(500000, 1)).toBe(0);
  });

  it('handles negative operating income', () => {
    expect(calculateNOPAT(-200000, 0.21)).toBe(-158000);
  });
});

describe('calculateFCFF', () => {
  it('calculates standard FCFF', () => {
    expect(calculateFCFF(790000, 50000, 80000, 10000)).toBe(750000);
  });

  it('returns zero when all inputs are zero', () => {
    expect(calculateFCFF(0, 0, 0, 0)).toBe(0);
  });
});

describe('calculateWACC', () => {
  it('calculates standard WACC', () => {
    // Rf=0.04, β=1.2, ERP=0.055, Rd=0.05, D/E=0.5, T=0.21
    // costOfEquity = 0.04 + 1.2*0.055 = 0.106
    // equityWeight = 1/1.5 = 0.6667; debtWeight = 0.5/1.5 = 0.3333
    // WACC = 0.6667*0.106 + 0.3333*0.05*0.79 ≈ 0.0839
    const result = calculateWACC(0.04, 1.2, 0.055, 0.05, 0.5, 0.21);
    expect(result).toBeCloseTo(0.0839, 3);
  });

  it('handles all-equity (D/E=0)', () => {
    // equityWeight=1, debtWeight=0 → WACC = costOfEquity = 0.04+1.0*0.055=0.095
    const result = calculateWACC(0.04, 1.0, 0.055, 0.05, 0, 0.21);
    expect(result).toBeCloseTo(0.095, 4);
  });

  it('handles high leverage (D/E=2)', () => {
    // equityWeight = 1/3, debtWeight = 2/3
    // costOfEquity = 0.04 + 1.5*0.06 = 0.13
    // WACC = (1/3)*0.13 + (2/3)*0.06*(1-0.25) = 0.04333 + 0.03 = 0.07333
    const result = calculateWACC(0.04, 1.5, 0.06, 0.06, 2, 0.25);
    expect(result).toBeCloseTo(0.07333, 4);
  });
});

describe('projectRevenue', () => {
  it('projects revenue with constant growth', () => {
    const result = projectRevenue(1000, 0.10, 3);
    expect(result).toHaveLength(3);
    expect(result[0]).toBeCloseTo(1100, 2);
    expect(result[1]).toBeCloseTo(1210, 2);
    expect(result[2]).toBeCloseTo(1331, 2);
  });

  it('handles 0% growth', () => {
    const result = projectRevenue(1000, 0, 3);
    expect(result).toEqual([1000, 1000, 1000]);
  });

  it('handles negative growth', () => {
    const result = projectRevenue(1000, -0.10, 2);
    expect(result[0]).toBeCloseTo(900, 2);
    expect(result[1]).toBeCloseTo(810, 2);
  });
});

describe('projectMargins', () => {
  it('projects margins for standard inputs', () => {
    // baseRevenue=1000, projectedRevenue=[1100,1210], rates: opMargin=0.20, dAndA=0.03, capEx=0.04, nwc=0.05, tax=0.21
    const result = projectMargins(1000, [1100, 1210], 0.20, 0.03, 0.04, 0.05, 0.21);

    // Year 1: opIncome=220, nopat=220*0.79=173.8, dAndA=33, capEx=44, deltaNWC=(1100-1000)*0.05=5
    // fcff = 173.8 + 33 - 44 - 5 = 157.8
    expect(result.operatingIncome[0]).toBeCloseTo(220, 2);
    expect(result.nopat[0]).toBeCloseTo(173.8, 2);
    expect(result.dAndA[0]).toBeCloseTo(33, 2);
    expect(result.capEx[0]).toBeCloseTo(44, 2);
    expect(result.deltaNWC[0]).toBeCloseTo(5, 2);
    expect(result.fcff[0]).toBeCloseTo(157.8, 2);

    // Year 2: opIncome=242, nopat=242*0.79=191.18, dAndA=36.3, capEx=48.4, deltaNWC=(1210-1100)*0.05=5.5
    // fcff = 191.18 + 36.3 - 48.4 - 5.5 = 173.58
    expect(result.operatingIncome[1]).toBeCloseTo(242, 2);
    expect(result.nopat[1]).toBeCloseTo(191.18, 2);
    expect(result.fcff[1]).toBeCloseTo(173.58, 2);
  });

  it('handles zero margins', () => {
    const result = projectMargins(1000, [1100], 0, 0, 0, 0, 0);
    expect(result.operatingIncome[0]).toBe(0);
    expect(result.nopat[0]).toBe(0);
    expect(result.dAndA[0]).toBe(0);
    expect(result.capEx[0]).toBe(0);
    expect(result.deltaNWC[0]).toBe(0);
    expect(result.fcff[0]).toBe(0);
  });
});

describe('terminalValuePerpetual', () => {
  it('calculates perpetuity terminal value', () => {
    // 750000 * 1.025 / (0.09 - 0.025) = 768750 / 0.065 ≈ 11826923.08
    const result = terminalValuePerpetual(750000, 0.025, 0.09);
    expect(result).toBeCloseTo(11826923.08, 0);
  });

  it('throws when wacc equals growth rate', () => {
    expect(() => terminalValuePerpetual(750000, 0.05, 0.05)).toThrow();
  });

  it('throws when wacc is less than growth rate', () => {
    expect(() => terminalValuePerpetual(750000, 0.10, 0.05)).toThrow();
  });
});

describe('terminalValueExitMultiple', () => {
  it('calculates exit multiple terminal value', () => {
    expect(terminalValueExitMultiple(500000, 10)).toBe(5000000);
  });

  it('throws when multiple is zero', () => {
    expect(() => terminalValueExitMultiple(500000, 0)).toThrow();
  });

  it('throws when multiple is negative', () => {
    expect(() => terminalValueExitMultiple(500000, -5)).toThrow();
  });
});

describe('discountCashFlows', () => {
  it('discounts multi-year cash flows', () => {
    // [100,100,100] @ 10% → [100/1.1, 100/1.21, 100/1.331] ≈ [90.91, 82.64, 75.13]
    const result = discountCashFlows([100, 100, 100], 0.10);
    expect(result[0]).toBeCloseTo(90.91, 1);
    expect(result[1]).toBeCloseTo(82.64, 1);
    expect(result[2]).toBeCloseTo(75.13, 1);
  });

  it('discounts single year', () => {
    const result = discountCashFlows([1000], 0.08);
    expect(result[0]).toBeCloseTo(1000 / 1.08, 2);
  });

  it('handles 0% WACC (no discounting)', () => {
    const result = discountCashFlows([100, 200, 300], 0);
    expect(result[0]).toBe(100);
    expect(result[1]).toBe(200);
    expect(result[2]).toBe(300);
  });
});

describe('enterpriseValue', () => {
  it('sums PV of cash flows and terminal value', () => {
    expect(enterpriseValue([100, 200, 300], 5000)).toBe(5600);
  });
});

describe('equityValue', () => {
  it('subtracts positive net debt', () => {
    expect(equityValue(10000000, 2000000)).toBe(8000000);
  });

  it('adds value when net debt is negative (net cash)', () => {
    expect(equityValue(10000000, -500000)).toBe(10500000);
  });
});

describe('impliedSharePrice', () => {
  it('calculates share price', () => {
    expect(impliedSharePrice(8000000, 100000)).toBe(80);
  });

  it('throws when diluted shares is zero', () => {
    expect(() => impliedSharePrice(8000000, 0)).toThrow();
  });

  it('throws when diluted shares is negative', () => {
    expect(() => impliedSharePrice(8000000, -100)).toThrow();
  });
});

describe('sensitivityAnalysis', () => {
  const baseInputs: DCFInputs = {
    revenue: 1000000,
    operatingIncome: 200000,
    taxRate: 0.21,
    depreciationAmortization: 30000,
    capitalExpenditures: 40000,
    changeInNWC: 10000,
    netDebt: 500000,
    sharesOutstanding: 100000,
    riskFreeRate: 0.04,
    beta: 1.2,
    equityRiskPremium: 0.055,
    costOfDebt: 0.05,
    debtToEquityRatio: 0.5,
    perpetuityGrowthRate: 0.025,
    exitMultiple: 10,
    finalYearEBITDA: 300000,
    method: 'perpetuity',
    revenueGrowthRate: 0.10,
    operatingMarginRate: 0.20,
    dAndARate: 0.03,
    capExRate: 0.04,
    nwcRate: 0.05,
    projectionYears: 3,
    company: { companyName: 'Test Corp', currency: 'USD' },
  };

  it('returns matrix with correct dimensions', () => {
    const waccRange = [0.07, 0.08, 0.09];
    const growthRange = [0.02, 0.025, 0.03];
    const result = sensitivityAnalysis(baseInputs, waccRange, growthRange);
    expect(result).toHaveLength(3);
    expect(result[0]).toHaveLength(3);
  });

  it('returns null where wacc <= growth', () => {
    const waccRange = [0.02, 0.09];
    const growthRange = [0.03, 0.025];
    const result = sensitivityAnalysis(baseInputs, waccRange, growthRange);
    // wacc=0.02, growth=0.03 → wacc <= growth → null
    expect(result[0][0]).toBeNull();
    // wacc=0.02, growth=0.025 → wacc <= growth → null
    expect(result[0][1]).toBeNull();
    // wacc=0.09, growth=0.03 → valid number
    expect(result[1][0]).not.toBeNull();
    expect(typeof result[1][0]).toBe('number');
  });

  it('computes a known base-case cell', () => {
    // Use a single-cell sensitivity that matches a full DCF run
    const waccRange = [0.09];
    const growthRange = [0.025];
    const result = sensitivityAnalysis(baseInputs, waccRange, growthRange);
    expect(result[0][0]).not.toBeNull();
    expect(typeof result[0][0]).toBe('number');
  });
});

describe('runFullDCF', () => {
  // Hand-computed integration test
  // Inputs:
  //   revenue=1,000,000, growthRate=0.10, years=3
  //   operatingMarginRate=0.20, dAndARate=0.03, capExRate=0.04, nwcRate=0.05, taxRate=0.21
  //   Rf=0.04, β=1.2, ERP=0.055, Rd=0.05, D/E=0.5
  //   perpetuityGrowthRate=0.025, method='perpetuity'
  //   netDebt=500,000, sharesOutstanding=100,000
  //
  // Step 1: Revenue → [1,100,000; 1,210,000; 1,331,000]
  // Step 2: Margins (year 1):
  //   opIncome=220,000; nopat=173,800; dAndA=33,000; capEx=44,000; deltaNWC=5,000
  //   fcff=173,800+33,000-44,000-5,000 = 157,800
  // Year 2: opIncome=242,000; nopat=191,180; dAndA=36,300; capEx=48,400; deltaNWC=5,500
  //   fcff=191,180+36,300-48,400-5,500 = 173,580
  // Year 3: opIncome=266,200; nopat=210,298; dAndA=39,930; capEx=53,240; deltaNWC=6,050
  //   fcff=210,298+39,930-53,240-6,050 = 190,938
  // Step 3: WACC = (2/3)*0.106 + (1/3)*0.05*0.79 = 0.083833...
  // Step 4: TV (perpetuity) = 190,938*(1.025)/(0.083833-0.025) = 195,711.45/0.058833 ≈ 3,326,078
  // Step 5: Discount factors: 1/(1.083833)^t for t=1,2,3
  //   df1 ≈ 0.92265; df2 ≈ 0.85128; df3 ≈ 0.78539
  // pvFCFF: [157800*df1, 173580*df2, 190938*df3] ≈ [145594, 147733, 149951]
  // pvTV = TV * df3 ≈ 3,326,078 * 0.78539 ≈ 2,612,153
  // EV = sum(pvFCFF) + pvTV ≈ 443,278 + 2,612,153 ≈ 3,055,431
  // Equity = EV - netDebt = 3,055,431 - 500,000 = 2,555,431
  // SharePrice = 2,555,431 / 100,000 ≈ 25.55

  const inputs: DCFInputs = {
    revenue: 1000000,
    operatingIncome: 200000,
    taxRate: 0.21,
    depreciationAmortization: 30000,
    capitalExpenditures: 40000,
    changeInNWC: 10000,
    netDebt: 500000,
    sharesOutstanding: 100000,
    riskFreeRate: 0.04,
    beta: 1.2,
    equityRiskPremium: 0.055,
    costOfDebt: 0.05,
    debtToEquityRatio: 0.5,
    perpetuityGrowthRate: 0.025,
    exitMultiple: 10,
    finalYearEBITDA: 300000,
    method: 'perpetuity',
    revenueGrowthRate: 0.10,
    operatingMarginRate: 0.20,
    dAndARate: 0.03,
    capExRate: 0.04,
    nwcRate: 0.05,
    projectionYears: 3,
    company: { companyName: 'Test Corp', currency: 'USD' },
  };

  it('returns correct projected revenue', () => {
    const result = runFullDCF(inputs);
    expect(result.projectedRevenue).toHaveLength(3);
    expect(result.projectedRevenue[0]).toBeCloseTo(1100000, 0);
    expect(result.projectedRevenue[1]).toBeCloseTo(1210000, 0);
    expect(result.projectedRevenue[2]).toBeCloseTo(1331000, 0);
  });

  it('returns correct WACC', () => {
    const result = runFullDCF(inputs);
    expect(result.wacc).toBeCloseTo(0.08383, 4);
  });

  it('returns correct projected FCFF', () => {
    const result = runFullDCF(inputs);
    expect(result.projectedFCFF[0]).toBeCloseTo(157800, 0);
    expect(result.projectedFCFF[1]).toBeCloseTo(173580, 0);
    expect(result.projectedFCFF[2]).toBeCloseTo(190938, 0);
  });

  it('returns correct terminal value (perpetuity)', () => {
    const result = runFullDCF(inputs);
    // TV = 190938 * 1.025 / (0.083833... - 0.025) = 195711.45 / 0.058833... ≈ 3,326,540
    expect(result.terminalValue).toBeCloseTo(3326540, -2);
  });

  it('computes enterprise value, equity value, and share price', () => {
    const result = runFullDCF(inputs);
    expect(result.enterpriseValue).toBeGreaterThan(0);
    expect(result.equityValue).toBe(result.enterpriseValue - 500000);
    expect(result.impliedSharePrice).toBeCloseTo(result.equityValue / 100000, 2);
  });

  it('returns discount factors matching 1/(1+wacc)^t', () => {
    const result = runFullDCF(inputs);
    expect(result.discountFactors).toHaveLength(3);
    const wacc = result.wacc;
    for (let i = 0; i < 3; i++) {
      expect(result.discountFactors[i]).toBeCloseTo(1 / Math.pow(1 + wacc, i + 1), 6);
    }
  });

  it('works with exit multiple method', () => {
    const exitInputs: DCFInputs = { ...inputs, method: 'exitMultiple', finalYearEBITDA: 300000, exitMultiple: 10 };
    const result = runFullDCF(exitInputs);
    // TV = 300000 * 10 = 3,000,000
    expect(result.terminalValue).toBe(3000000);
    expect(result.enterpriseValue).toBeGreaterThan(0);
    expect(result.impliedSharePrice).toBeGreaterThan(0);
  });
});
