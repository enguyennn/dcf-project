import type { DCFInputs, DCFOutputs } from '../models/financialTypes';

/** ITEM-012: NOPAT = Operating Income × (1 − Tax Rate) */
export function calculateNOPAT(operatingIncome: number, taxRate: number): number {
  return operatingIncome * (1 - taxRate);
}

/** ITEM-013: FCFF = NOPAT + D&A − CapEx − ΔNWC */
export function calculateFCFF(nopat: number, dAndA: number, capEx: number, deltaNWC: number): number {
  return nopat + dAndA - capEx - deltaNWC;
}

/** ITEM-014: Weighted Average Cost of Capital */
export function calculateWACC(
  riskFreeRate: number,
  beta: number,
  equityRiskPremium: number,
  costOfDebt: number,
  debtToEquityRatio: number,
  taxRate: number,
): number {
  const costOfEquity = riskFreeRate + beta * equityRiskPremium;
  const equityWeight = 1 / (1 + debtToEquityRatio);
  const debtWeight = debtToEquityRatio / (1 + debtToEquityRatio);
  return equityWeight * costOfEquity + debtWeight * costOfDebt * (1 - taxRate);
}

/** ITEM-015: Compound revenue projection for each year t=1..years */
export function projectRevenue(baseRevenue: number, growthRate: number, years: number): number[] {
  const result: number[] = [];
  for (let t = 1; t <= years; t++) {
    result.push(baseRevenue * Math.pow(1 + growthRate, t));
  }
  return result;
}

/**
 * ITEM-016: Project operating margins and free cash flows.
 * Design decision: baseRevenue is the first parameter because year-1 deltaNWC
 * requires the pre-projection revenue (prevRev for i=0 = baseRevenue).
 */
export function projectMargins(
  baseRevenue: number,
  projectedRevenue: number[],
  operatingMarginRate: number,
  dAndARate: number,
  capExRate: number,
  nwcRate: number,
  taxRate: number,
): {
  operatingIncome: number[];
  nopat: number[];
  dAndA: number[];
  capEx: number[];
  deltaNWC: number[];
  fcff: number[];
} {
  const operatingIncome: number[] = [];
  const nopat: number[] = [];
  const dAndA: number[] = [];
  const capEx: number[] = [];
  const deltaNWC: number[] = [];
  const fcff: number[] = [];

  for (let i = 0; i < projectedRevenue.length; i++) {
    const rev = projectedRevenue[i];
    const prevRev = i === 0 ? baseRevenue : projectedRevenue[i - 1];

    const oi = rev * operatingMarginRate;
    const np = calculateNOPAT(oi, taxRate);
    const da = rev * dAndARate;
    const cx = rev * capExRate;
    const dnwc = (rev - prevRev) * nwcRate;
    const cf = calculateFCFF(np, da, cx, dnwc);

    operatingIncome.push(oi);
    nopat.push(np);
    dAndA.push(da);
    capEx.push(cx);
    deltaNWC.push(dnwc);
    fcff.push(cf);
  }

  return { operatingIncome, nopat, dAndA, capEx, deltaNWC, fcff };
}

/** ITEM-017: Gordon Growth Model terminal value */
export function terminalValuePerpetual(finalFCFF: number, growthRate: number, wacc: number): number {
  if (wacc <= growthRate) {
    throw new Error('WACC must be greater than perpetuity growth rate');
  }
  return (finalFCFF * (1 + growthRate)) / (wacc - growthRate);
}

/** ITEM-018: Exit multiple terminal value */
export function terminalValueExitMultiple(finalEBITDA: number, multiple: number): number {
  if (multiple <= 0) {
    throw new Error('Exit multiple must be greater than zero');
  }
  return finalEBITDA * multiple;
}

/** ITEM-019: Discount each cash flow to present value */
export function discountCashFlows(cashFlows: number[], wacc: number): number[] {
  return cashFlows.map((cf, i) => cf / Math.pow(1 + wacc, i + 1));
}

/** ITEM-020: Enterprise Value = sum(PV of FCFFs) + PV of Terminal Value */
export function enterpriseValue(pvCashFlows: number[], pvTerminalValue: number): number {
  return pvCashFlows.reduce((sum, pv) => sum + pv, 0) + pvTerminalValue;
}

/** ITEM-021: Equity Value = Enterprise Value − Net Debt */
export function equityValue(ev: number, netDebt: number): number {
  return ev - netDebt;
}

/** ITEM-022: Implied Share Price = Equity Value / Diluted Shares */
export function impliedSharePrice(eqValue: number, dilutedShares: number): number {
  if (dilutedShares <= 0) {
    throw new Error('Diluted shares outstanding must be greater than zero');
  }
  return eqValue / dilutedShares;
}

/**
 * ITEM-023: Sensitivity analysis matrix.
 * Design decision: baseInputs is typed as DCFInputs so the function can extract
 * all projection/financial parameters needed. WACC and perpetuity growth rate are
 * overridden per cell from the provided ranges; all other inputs stay constant.
 * Uses lower-level functions (not runFullDCF) because we need to substitute the
 * WACC value directly rather than re-derive it from components.
 */
export function sensitivityAnalysis(
  baseInputs: DCFInputs,
  waccRange: number[],
  growthRange: number[],
): (number | null)[][] {
  const revenues = projectRevenue(baseInputs.revenue, baseInputs.revenueGrowthRate, baseInputs.projectionYears);
  const margins = projectMargins(
    baseInputs.revenue,
    revenues,
    baseInputs.operatingMarginRate,
    baseInputs.dAndARate,
    baseInputs.capExRate,
    baseInputs.nwcRate,
    baseInputs.taxRate,
  );
  const finalFCFF = margins.fcff[margins.fcff.length - 1];

  return waccRange.map((wacc) =>
    growthRange.map((growth) => {
      if (wacc <= growth) return null;
      const tv = terminalValuePerpetual(finalFCFF, growth, wacc);
      const pvFCFFs = discountCashFlows(margins.fcff, wacc);
      const pvTV = tv / Math.pow(1 + wacc, baseInputs.projectionYears);
      const ev = enterpriseValue(pvFCFFs, pvTV);
      const equity = equityValue(ev, baseInputs.netDebt);
      if (baseInputs.sharesOutstanding <= 0) return null;
      return equity / baseInputs.sharesOutstanding;
    }),
  );
}

/**
 * ITEM-024: Full DCF orchestrator.
 * Maps DCFInputs fields to the calculation pipeline and returns a complete DCFOutputs.
 */
export function runFullDCF(inputs: DCFInputs): DCFOutputs {
  const projectedRevenue = projectRevenue(inputs.revenue, inputs.revenueGrowthRate, inputs.projectionYears);

  const margins = projectMargins(
    inputs.revenue,
    projectedRevenue,
    inputs.operatingMarginRate,
    inputs.dAndARate,
    inputs.capExRate,
    inputs.nwcRate,
    inputs.taxRate,
  );

  const wacc = calculateWACC(
    inputs.riskFreeRate,
    inputs.beta,
    inputs.equityRiskPremium,
    inputs.costOfDebt,
    inputs.debtToEquityRatio,
    inputs.taxRate,
  );

  const terminalValue =
    inputs.method === 'perpetuity'
      ? terminalValuePerpetual(margins.fcff[margins.fcff.length - 1], inputs.perpetuityGrowthRate, wacc)
      : terminalValueExitMultiple(inputs.finalYearEBITDA, inputs.exitMultiple);

  const discountFactors = projectedRevenue.map((_, i) => 1 / Math.pow(1 + wacc, i + 1));
  const pvFCFF = discountCashFlows(margins.fcff, wacc);
  const pvTerminalValue = terminalValue * discountFactors[discountFactors.length - 1];
  const ev = enterpriseValue(pvFCFF, pvTerminalValue);
  const equity = equityValue(ev, inputs.netDebt);
  const sharePrice = impliedSharePrice(equity, inputs.sharesOutstanding);

  return {
    projectedRevenue,
    projectedFCFF: margins.fcff,
    discountFactors,
    pvFCFF,
    terminalValue,
    pvTerminalValue,
    enterpriseValue: ev,
    equityValue: equity,
    impliedSharePrice: sharePrice,
    wacc,
  };
}

/**
 * ITEM-064: Generic sensitivity matrix over any two numeric DCFInputs fields.
 * Outer array indexed by yValues (rows), inner by xValues (cols).
 */
export function sensitivityMatrix(
  base: DCFInputs,
  xField: keyof DCFInputs,
  xValues: number[],
  yField: keyof DCFInputs,
  yValues: number[],
): (number | null)[][] {
  return yValues.map((yVal) =>
    xValues.map((xVal) => {
      try {
        const overridden = { ...base, company: { ...base.company }, [xField]: xVal, [yField]: yVal };
        return runFullDCF(overridden).impliedSharePrice;
      } catch {
        return null;
      }
    }),
  );
}
