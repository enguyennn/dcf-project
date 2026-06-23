import type { AssumptionDefaults } from '../models/financialTypes';

/** Educational default assumptions for DCF modeling. */
export const DEFAULT_ASSUMPTIONS: AssumptionDefaults = {
  // WACC components
  riskFreeRate: 0.04, // ≈10Y US Treasury yield
  beta: 1.0, // Market average (S&P 500 beta)
  equityRiskPremium: 0.055, // Historical average equity risk premium
  costOfDebt: 0.05, // Typical investment-grade corporate borrowing rate
  debtToEquityRatio: 0.5, // Moderate leverage (1/3 debt, 2/3 equity)

  // Tax
  taxRate: 0.21, // US federal corporate tax rate

  // Terminal value assumptions
  perpetuityGrowthRate: 0.025, // ≈Long-term GDP growth rate
  exitMultiple: 10, // Typical EV/EBITDA multiple

  // Projection assumptions
  revenueGrowthRate: 0.05, // 5% annual revenue growth
  operatingMarginRate: 0.15, // 15% operating margin
  dAndARate: 0.03, // D&A as 3% of revenue
  capExRate: 0.04, // CapEx as 4% of revenue
  nwcRate: 0.01, // Change in NWC as 1% of revenue growth
  projectionYears: 5, // 5-year explicit forecast period
};
