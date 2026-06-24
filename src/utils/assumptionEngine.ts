import type { DCFInputs } from '../models/financialTypes';
import { DEFAULT_ASSUMPTIONS } from '../data/defaultAssumptions';

/**
 * Complete base DCFInputs built from DEFAULT_ASSUMPTIONS plus neutral defaults
 * for company-specific fields that have no meaningful default.
 *
 * FinancialData numeric fields → 0 (user must provide real values).
 * finalYearEBITDA → 0 (derived at calculation time).
 * method → 'perpetuity' (default terminal value approach).
 * company → minimal placeholder with USD currency.
 */
const COMPLETE_BASE: DCFInputs = {
  ...DEFAULT_ASSUMPTIONS,
  revenue: 0,
  operatingIncome: 0,
  depreciationAmortization: 0,
  capitalExpenditures: 0,
  changeInNWC: 0,
  netDebt: 0,
  sharesOutstanding: 0,
  finalYearEBITDA: 0,
  method: 'perpetuity',
  company: { companyName: '', currency: 'USD' },
};

/**
 * Merges user-provided partial inputs over a complete base DCFInputs.
 * Returns a fully-populated DCFInputs object.
 */
export function mergeAssumptions(userInputs: Partial<DCFInputs>): DCFInputs {
  const { company: userCompany, ...restInputs } = userInputs;
  return {
    ...COMPLETE_BASE,
    ...restInputs,
    company: {
      ...COMPLETE_BASE.company,
      ...userCompany,
    },
  };
}

/**
 * Creates a scenario variant by adjusting growth and discount rate assumptions.
 *
 * WACC interpretation: WACC is a derived value (not stored as a field on DCFInputs).
 * To achieve a +/- 1% WACC effect, we adjust `riskFreeRate` as the lever,
 * since WACC = weighted-average of cost-of-equity (which includes riskFreeRate)
 * and after-tax cost-of-debt. Shifting riskFreeRate by ±0.01 shifts WACC by
 * approximately the same magnitude (exact effect depends on capital weights).
 */
export function createScenario(
  base: DCFInputs,
  scenario: 'conservative' | 'base' | 'optimistic'
): DCFInputs {
  if (scenario === 'base') {
    return { ...base, company: { ...base.company } };
  }

  if (scenario === 'conservative') {
    return {
      ...base,
      company: { ...base.company },
      revenueGrowthRate: base.revenueGrowthRate - 0.02,
      riskFreeRate: base.riskFreeRate + 0.01, // WACC +1% via riskFreeRate lever
    };
  }

  // optimistic
  return {
    ...base,
    company: { ...base.company },
    revenueGrowthRate: base.revenueGrowthRate + 0.02,
    riskFreeRate: base.riskFreeRate - 0.01, // WACC -1% via riskFreeRate lever
  };
}
