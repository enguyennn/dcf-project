import { describe, it, expect } from 'vitest';
import { parsePlainText } from '../src/utils/parsePlainText';

describe('parsePlainText', () => {
  it('parses standard colon-separated format', () => {
    const result = parsePlainText('Revenue: 1,000,000');
    expect(result.parsed.revenue).toBe(1000000);
    expect(result.errors).toHaveLength(0);
  });

  it('parses alias "Sales" to revenue field', () => {
    const result = parsePlainText('Sales: 500K');
    expect(result.parsed.revenue).toBe(500000);
    expect(result.errors).toHaveLength(0);
  });

  it('handles M suffix (millions)', () => {
    const result = parsePlainText('Revenue: 2.5M');
    expect(result.parsed.revenue).toBe(2500000);
  });

  it('handles B suffix (billions)', () => {
    const result = parsePlainText('Revenue: 1.2B');
    expect(result.parsed.revenue).toBe(1200000000);
  });

  it('handles K suffix case-insensitive', () => {
    const result = parsePlainText('Net Debt: 750k');
    expect(result.parsed.netDebt).toBe(750000);
  });

  it('collects unrecognized non-blank lines as errors', () => {
    const result = parsePlainText('Unknown field: 123\nGarbage line');
    expect(result.errors).toContain('Unknown field: 123');
    expect(result.errors).toContain('Garbage line');
    expect(Object.keys(result.parsed)).toHaveLength(0);
  });

  it('returns empty parsed and empty errors for empty input', () => {
    const result = parsePlainText('');
    expect(result.parsed).toEqual({});
    expect(result.errors).toEqual([]);
  });

  it('skips blank and whitespace-only lines without adding to errors', () => {
    const result = parsePlainText('Revenue: 100\n\n   \n\nEBIT: 50');
    expect(result.parsed.revenue).toBe(100);
    expect(result.parsed.operatingIncome).toBe(50);
    expect(result.errors).toHaveLength(0);
  });

  it('parses multiple fields from multi-line input', () => {
    const input = `Revenue: 5,000,000
Operating Income: 750,000
Tax Rate: 0.21
CapEx: 200K
Shares Outstanding: 10M`;
    const result = parsePlainText(input);
    expect(result.parsed.revenue).toBe(5000000);
    expect(result.parsed.operatingIncome).toBe(750000);
    expect(result.parsed.taxRate).toBe(0.21);
    expect(result.parsed.capitalExpenditures).toBe(200000);
    expect(result.parsed.sharesOutstanding).toBe(10000000);
    expect(result.errors).toHaveLength(0);
  });

  it('strips commas from numeric values', () => {
    const result = parsePlainText('Revenue: 1,234,567');
    expect(result.parsed.revenue).toBe(1234567);
  });

  it('handles equals sign separator', () => {
    const result = parsePlainText('revenue = 1M');
    expect(result.parsed.revenue).toBe(1000000);
  });

  it('matches D&A alias', () => {
    const result = parsePlainText('D&A: 300,000');
    expect(result.parsed.depreciationAmortization).toBe(300000);
  });

  it('matches "Change in NWC" alias', () => {
    const result = parsePlainText('Change in NWC: 50000');
    expect(result.parsed.changeInNWC).toBe(50000);
  });

  it('is case-insensitive for labels', () => {
    const result = parsePlainText('REVENUE: 100\nebit: 50');
    expect(result.parsed.revenue).toBe(100);
    expect(result.parsed.operatingIncome).toBe(50);
  });

  it('handles space-separated key and value', () => {
    const result = parsePlainText('Revenue 5000000');
    expect(result.parsed.revenue).toBe(5000000);
  });
});
