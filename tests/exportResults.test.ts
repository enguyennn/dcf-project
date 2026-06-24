import { describe, it, expect } from 'vitest';
import { generateCSV } from '../src/utils/exportResults';
import { mergeAssumptions } from '../src/utils/assumptionEngine';
import { runFullDCF } from '../src/utils/dcfCalculations';
import type { DCFInputs, DCFOutputs } from '../src/models/financialTypes';

describe('generateCSV', () => {
  const inputs: DCFInputs = mergeAssumptions({
    revenue: 1000000,
    operatingIncome: 200000,
    sharesOutstanding: 100000,
    depreciationAmortization: 50000,
    capitalExpenditures: 80000,
    changeInNWC: 10000,
    netDebt: 500000,
    company: { companyName: 'TestCo', currency: 'USD' },
  });
  const outputs: DCFOutputs = runFullDCF(inputs);

  it('contains section headers', () => {
    const csv = generateCSV(inputs, outputs);
    expect(csv).toContain('Input Assumptions');
    expect(csv).toContain('Year-by-Year Projections');
    expect(csv).toContain('Summary Metrics');
  });

  it('contains an assumptions row for revenue', () => {
    const csv = generateCSV(inputs, outputs);
    expect(csv).toContain('revenue');
    expect(csv).toContain('1000000');
  });

  it('has projection row count equal to projectionYears', () => {
    const csv = generateCSV(inputs, outputs);
    const lines = csv.split('\n');
    // Find the projections header line
    const projIdx = lines.findIndex((l) => l.includes('Year-by-Year Projections'));
    // Next line is the column header, then projectionYears data rows
    const headerIdx = projIdx + 1;
    let dataRows = 0;
    for (let i = headerIdx + 1; i < lines.length; i++) {
      if (lines[i].trim() === '' || lines[i].includes('Summary Metrics')) break;
      dataRows++;
    }
    expect(dataRows).toBe(inputs.projectionYears);
  });

  it('contains the implied share price value', () => {
    const csv = generateCSV(inputs, outputs);
    expect(csv).toContain(outputs.impliedSharePrice.toString());
  });

  it('correctly quotes a field containing a comma (RFC-4180)', () => {
    const commaInputs = mergeAssumptions({
      revenue: 1000000,
      sharesOutstanding: 100000,
      company: { companyName: 'Acme, Inc.', currency: 'USD' },
    });
    const commaOutputs = runFullDCF(commaInputs);
    const csv = generateCSV(commaInputs, commaOutputs);
    expect(csv).toContain('"Acme, Inc."');
  });
});
