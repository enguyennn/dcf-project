export interface FinancialData {
  revenue: number;
  operatingIncome: number;
  taxRate: number;
  depreciationAmortization: number;
  capitalExpenditures: number;
  changeInNWC: number;
  netDebt: number;
  sharesOutstanding: number;
}

export interface WACCInputs {
  riskFreeRate: number;
  beta: number;
  equityRiskPremium: number;
  costOfDebt: number;
  debtToEquityRatio: number;
}

export interface TerminalValueInputs {
  perpetuityGrowthRate: number;
  exitMultiple: number;
  finalYearEBITDA: number;
  method: 'perpetuity' | 'exitMultiple';
}

export interface ProjectionInputs {
  revenueGrowthRate: number;
  operatingMarginRate: number;
  dAndARate: number;
  capExRate: number;
  nwcRate: number;
  projectionYears: number;
}

export interface CompanyInfo {
  companyName: string;
  tickerSymbol?: string;
  industry?: string;
  currency: string;
}

/**
 * AssumptionDefaults covers exactly the fields that have sensible educational
 * defaults (ITEM-011): WACCInputs + ProjectionInputs + the two scalar TV fields
 * (perpetuityGrowthRate, exitMultiple) + taxRate.
 *
 * Rationale: FinancialData fields (revenue, operatingIncome, netDebt, etc.) and
 * CompanyInfo are company-specific and have no meaningful default.
 * TerminalValueInputs.finalYearEBITDA and .method are calculation-time values
 * that depend on projections, not user-configurable assumptions at default time.
 * taxRate lives canonically in FinancialData but is also a default assumption
 * (US corporate rate) so it's picked into this type.
 */
export type AssumptionDefaults = WACCInputs &
  ProjectionInputs &
  Pick<TerminalValueInputs, 'perpetuityGrowthRate' | 'exitMultiple'> &
  Pick<FinancialData, 'taxRate'>;

/**
 * DCFInputs aggregates all input interfaces needed for a full DCF run.
 * taxRate is inherited from FinancialData (single canonical location).
 */
export interface DCFInputs extends FinancialData, WACCInputs, TerminalValueInputs, ProjectionInputs {
  company: CompanyInfo;
}

export interface DCFOutputs {
  projectedRevenue: number[];
  projectedFCFF: number[];
  discountFactors: number[];
  pvFCFF: number[];
  terminalValue: number;
  pvTerminalValue: number;
  enterpriseValue: number;
  equityValue: number;
  impliedSharePrice: number;
  wacc: number;
}

export interface ValidationWarning {
  field: string;
  message: string;
  severity: 'error' | 'warning';
}
