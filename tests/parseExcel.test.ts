import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as XLSX from 'xlsx';

// Mock FileReader for node environment
class MockFileReader {
  onload: ((ev: { target: { result: ArrayBuffer } }) => void) | null = null;
  onerror: ((ev: { target: { error: Error } }) => void) | null = null;

  readAsArrayBuffer(_file: unknown) {
    // By default, resolve with the file's __buffer property (test hook)
    const buffer = (_file as { __buffer: ArrayBuffer }).__buffer;
    setTimeout(() => {
      if (this.onload) {
        this.onload({ target: { result: buffer } });
      }
    }, 0);
  }
}

function createMockFile(buffer: ArrayBuffer): File {
  return { __buffer: buffer } as unknown as File;
}

function buildXlsxBuffer(aoa: unknown[][]): ArrayBuffer {
  const ws = XLSX.utils.aoa_to_sheet(aoa);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
  return XLSX.write(wb, { type: 'array', bookType: 'xlsx' }) as ArrayBuffer;
}

describe('parseExcel', () => {
  let parseExcel: typeof import('../src/utils/parseExcel').parseExcel;

  beforeEach(async () => {
    (globalThis as unknown as { FileReader: typeof MockFileReader }).FileReader = MockFileReader as unknown as typeof FileReader;
    // Fresh import to pick up the mock
    const mod = await import('../src/utils/parseExcel');
    parseExcel = mod.parseExcel;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('(a) maps standard headers to FinancialData fields', async () => {
    const buffer = buildXlsxBuffer([
      ['Revenue', 'EBIT', 'Shares Outstanding'],
      [1000000, 250000, 50000],
    ]);
    const file = createMockFile(buffer);
    const result = await parseExcel(file);

    expect(result.errors).toEqual([]);
    expect(result.parsed).toHaveLength(1);
    expect(result.parsed[0]).toEqual({
      revenue: 1000000,
      operatingIncome: 250000,
      sharesOutstanding: 50000,
    });
  });

  it('(b) maps alias headers correctly', async () => {
    const buffer = buildXlsxBuffer([
      ['Sales', 'Net Debt', 'Diluted Shares'],
      [500000, 100000, 25000],
    ]);
    const file = createMockFile(buffer);
    const result = await parseExcel(file);

    expect(result.errors).toEqual([]);
    expect(result.parsed).toHaveLength(1);
    expect(result.parsed[0]).toEqual({
      revenue: 500000,
      netDebt: 100000,
      sharesOutstanding: 25000,
    });
  });

  it('(c) multi-row sheet returns multiple parsed entries', async () => {
    const buffer = buildXlsxBuffer([
      ['Revenue', 'EBIT'],
      [1000, 200],
      [1100, 220],
      [1210, 242],
    ]);
    const file = createMockFile(buffer);
    const result = await parseExcel(file);

    expect(result.errors).toEqual([]);
    expect(result.parsed).toHaveLength(3);
    expect(result.parsed[0]).toEqual({ revenue: 1000, operatingIncome: 200 });
    expect(result.parsed[1]).toEqual({ revenue: 1100, operatingIncome: 220 });
    expect(result.parsed[2]).toEqual({ revenue: 1210, operatingIncome: 242 });
  });

  it('(d) unmapped header column is skipped', async () => {
    const buffer = buildXlsxBuffer([
      ['Revenue', 'Foo Bar', 'Shares Outstanding'],
      [5000, 9999, 100],
    ]);
    const file = createMockFile(buffer);
    const result = await parseExcel(file);

    expect(result.parsed).toHaveLength(1);
    expect(result.parsed[0]).toEqual({
      revenue: 5000,
      sharesOutstanding: 100,
    });
    // 'Foo Bar' column is silently skipped, no error for unmapped headers
  });

  it('(e) string cell with suffix like "1.5M" is parsed via parseNumericValue', async () => {
    const buffer = buildXlsxBuffer([
      ['Revenue', 'Net Debt'],
      ['1.5M', '200K'],
    ]);
    const file = createMockFile(buffer);
    const result = await parseExcel(file);

    expect(result.errors).toEqual([]);
    expect(result.parsed).toHaveLength(1);
    expect(result.parsed[0]).toEqual({
      revenue: 1500000,
      netDebt: 200000,
    });
  });

  it('(f) read failure returns parsed:[] and errors with message, does not throw', async () => {
    // Override FileReader to simulate failure
    class FailingFileReader {
      onload: (() => void) | null = null;
      onerror: ((ev: { target: { error: Error } }) => void) | null = null;

      readAsArrayBuffer(_file: unknown) {
        setTimeout(() => {
          if (this.onerror) {
            this.onerror({ target: { error: new Error('Read failed') } });
          }
        }, 0);
      }
    }
    (globalThis as unknown as { FileReader: typeof FailingFileReader }).FileReader = FailingFileReader as unknown as typeof FileReader;

    const file = createMockFile(new ArrayBuffer(0));
    const result = await parseExcel(file);

    expect(result.parsed).toEqual([]);
    expect(result.errors.length).toBeGreaterThan(0);
    expect(result.errors[0]).toContain('Read failed');
  });

  it('(f) empty sheet returns parsed:[] and errors with message', async () => {
    const buffer = buildXlsxBuffer([]);
    const file = createMockFile(buffer);
    const result = await parseExcel(file);

    expect(result.parsed).toEqual([]);
    expect(result.errors.length).toBeGreaterThan(0);
  });
});
