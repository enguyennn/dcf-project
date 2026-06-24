import type { DCFInputs, DCFOutputs } from '../models/financialTypes';

/** RFC-4180 CSV field escaping: wrap in quotes if contains comma, quote, or newline */
function escapeCSV(value: string): string {
  if (value.includes(',') || value.includes('"') || value.includes('\n')) {
    return '"' + value.replace(/"/g, '""') + '"';
  }
  return value;
}

/**
 * ITEM-063: Generate CSV text from DCF inputs and outputs.
 * Three sections: Input Assumptions, Year-by-Year Projections, Summary Metrics.
 */
export function generateCSV(inputs: DCFInputs, outputs: DCFOutputs): string {
  const lines: string[] = [];

  // Section 1: Input Assumptions
  lines.push('Input Assumptions');
  lines.push('Field,Value');
  const scalarFields: (keyof DCFInputs)[] = [
    'revenue', 'operatingIncome', 'taxRate', 'depreciationAmortization',
    'capitalExpenditures', 'changeInNWC', 'netDebt', 'sharesOutstanding',
    'riskFreeRate', 'beta', 'equityRiskPremium', 'costOfDebt', 'debtToEquityRatio',
    'perpetuityGrowthRate', 'exitMultiple', 'finalYearEBITDA', 'method',
    'revenueGrowthRate', 'operatingMarginRate', 'dAndARate', 'capExRate',
    'nwcRate', 'projectionYears',
  ];
  for (const field of scalarFields) {
    lines.push(`${escapeCSV(field)},${escapeCSV(String(inputs[field]))}`);
  }
  // Company fields
  lines.push(`company.companyName,${escapeCSV(inputs.company.companyName)}`);
  lines.push(`company.currency,${escapeCSV(inputs.company.currency)}`);
  if (inputs.company.tickerSymbol) lines.push(`company.tickerSymbol,${escapeCSV(inputs.company.tickerSymbol)}`);
  if (inputs.company.industry) lines.push(`company.industry,${escapeCSV(inputs.company.industry)}`);

  lines.push('');

  // Section 2: Year-by-Year Projections
  lines.push('Year-by-Year Projections');
  lines.push('Year,Revenue,FCFF,Discount Factor,PV of FCFF');
  for (let i = 0; i < outputs.projectedRevenue.length; i++) {
    lines.push(
      `${i + 1},${outputs.projectedRevenue[i]},${outputs.projectedFCFF[i]},${outputs.discountFactors[i]},${outputs.pvFCFF[i]}`,
    );
  }

  lines.push('');

  // Section 3: Summary Metrics
  lines.push('Summary Metrics');
  lines.push('Metric,Value');
  lines.push(`WACC,${outputs.wacc}`);
  lines.push(`Terminal Value,${outputs.terminalValue}`);
  lines.push(`PV Terminal Value,${outputs.pvTerminalValue}`);
  lines.push(`Enterprise Value,${outputs.enterpriseValue}`);
  lines.push(`Equity Value,${outputs.equityValue}`);
  lines.push(`Implied Share Price,${outputs.impliedSharePrice}`);

  return lines.join('\n');
}

/**
 * ITEM-063: Browser-only CSV download via Blob + temporary anchor.
 * Falls back to clipboard copy on failure (FM-007).
 * Returns outcome so the caller can notify the user.
 */
export async function downloadCSV(filename: string, csv: string): Promise<'downloaded' | 'clipboard' | 'failed'> {
  try {
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    return 'downloaded';
  } catch {
    try {
      await navigator.clipboard.writeText(csv);
      return 'clipboard';
    } catch {
      return 'failed';
    }
  }
}
