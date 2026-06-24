import type { DCFInputs, DCFOutputs, ValidationWarning } from '../models/financialTypes';
import { calculateWACC } from './dcfCalculations';

const NUMERIC_FIELDS: (keyof DCFInputs)[] = [
  'revenue', 'operatingIncome', 'taxRate', 'depreciationAmortization',
  'capitalExpenditures', 'changeInNWC', 'netDebt', 'sharesOutstanding',
  'riskFreeRate', 'beta', 'equityRiskPremium', 'costOfDebt', 'debtToEquityRatio',
  'perpetuityGrowthRate', 'exitMultiple', 'finalYearEBITDA',
  'revenueGrowthRate', 'operatingMarginRate', 'dAndARate', 'capExRate', 'nwcRate', 'projectionYears',
];

const FCFF_INAPPROPRIATE_INDUSTRIES = ['banking', 'insurance', 'real-estate'];

export function validateInputs(inputs: DCFInputs): ValidationWarning[] {
  const warnings: ValidationWarning[] = [];

  // Rule 7: required numeric fields must be valid numbers
  for (const field of NUMERIC_FIELDS) {
    const value = inputs[field];
    if (value === undefined || value === null || (typeof value === 'number' && isNaN(value))) {
      warnings.push({
        field,
        message: `${field} must be a valid number.`,
        severity: 'error',
      });
    }
  }

  // Rule 1: WACC ≤ perpetuityGrowthRate → error (perpetuity TV is invalid)
  const wacc = calculateWACC(
    inputs.riskFreeRate,
    inputs.beta,
    inputs.equityRiskPremium,
    inputs.costOfDebt,
    inputs.debtToEquityRatio,
    inputs.taxRate,
  );
  if (inputs.perpetuityGrowthRate >= wacc) {
    warnings.push({
      field: 'perpetuityGrowthRate',
      message: 'Perpetuity growth rate must be less than WACC; otherwise the terminal value formula produces a mathematically invalid (negative or infinite) result.',
      severity: 'error',
    });
  }

  // Rule 2: extreme revenue growth
  if (inputs.revenueGrowthRate > 0.30 || inputs.revenueGrowthRate < -0.20) {
    warnings.push({
      field: 'revenueGrowthRate',
      message: 'Revenue growth rate is extreme (>30% or <-20%). Verify this reflects realistic expectations.',
      severity: 'warning',
    });
  }

  // Rule 3: extreme operating margin
  if (inputs.operatingMarginRate > 0.50 || inputs.operatingMarginRate < -0.10) {
    warnings.push({
      field: 'operatingMarginRate',
      message: 'Operating margin is outside the typical range (-10% to 50%). Verify this is intentional.',
      severity: 'warning',
    });
  }

  // Rule 4: zero capEx with positive growth likely means missing data
  if (inputs.capExRate === 0 && inputs.revenueGrowthRate > 0) {
    warnings.push({
      field: 'capExRate',
      message: 'Capital expenditure rate is zero while revenue is growing — this likely indicates missing data.',
      severity: 'warning',
    });
  }

  // Rule 6: industry inappropriate for FCFF model
  const industry = inputs.company.industry?.toLowerCase();
  if (industry && FCFF_INAPPROPRIATE_INDUSTRIES.includes(industry)) {
    warnings.push({
      field: 'company.industry',
      message: 'FCFF-based DCF may be inappropriate for banking, insurance, or real-estate companies. Consider a dividend discount or residual income model.',
      severity: 'warning',
    });
  }

  return warnings;
}

export function validateOutputs(outputs: DCFOutputs): ValidationWarning[] {
  const warnings: ValidationWarning[] = [];

  // Rule 5: terminal value dominance
  if (outputs.terminalValue > 0.85 * outputs.enterpriseValue) {
    warnings.push({
      field: 'terminalValue',
      message: 'Terminal value exceeds 85% of enterprise value — the valuation is heavily dependent on long-term assumptions.',
      severity: 'warning',
    });
  }

  return warnings;
}
