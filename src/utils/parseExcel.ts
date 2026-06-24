import type { FinancialData } from '../models/financialTypes';
import { matchLabel, parseNumericValue } from './parsePlainText';

export async function parseExcel(
  file: File,
): Promise<{ parsed: Partial<FinancialData>[]; errors: string[] }> {
  let data: ArrayBuffer;
  try {
    data = await new Promise<ArrayBuffer>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (ev) => resolve(ev.target!.result as ArrayBuffer);
      reader.onerror = (ev) =>
        reject((ev as unknown as { target: { error: Error } }).target.error);
      reader.readAsArrayBuffer(file);
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to read file';
    return { parsed: [], errors: [message] };
  }

  const XLSX = await import('xlsx');
  let wb;
  try {
    wb = XLSX.read(data, { type: 'array' });
  } catch {
    return { parsed: [], errors: ['Failed to parse workbook'] };
  }

  const sheetName = wb.SheetNames[0];
  if (!sheetName) {
    return { parsed: [], errors: ['Workbook contains no sheets'] };
  }

  const sheet = wb.Sheets[sheetName];
  const rows = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1 });

  if (rows.length === 0) {
    return { parsed: [], errors: ['Sheet is empty'] };
  }

  const headerRow = rows[0] as unknown[];
  if (!headerRow || headerRow.length === 0) {
    return { parsed: [], errors: ['Sheet has no header row'] };
  }

  // Map column indices to FinancialData fields
  const columnMap: (keyof FinancialData | undefined)[] = headerRow.map((cell) => {
    if (typeof cell === 'string') return matchLabel(cell);
    return undefined;
  });

  const parsed: Partial<FinancialData>[] = [];
  const errors: string[] = [];

  for (let i = 1; i < rows.length; i++) {
    const row = rows[i] as unknown[];
    if (!row || row.length === 0) continue;

    const entry: Partial<FinancialData> = {};
    for (let col = 0; col < columnMap.length; col++) {
      const field = columnMap[col];
      if (!field) continue;

      const cell = row[col];
      if (cell === undefined || cell === null || cell === '') continue;

      if (typeof cell === 'number') {
        entry[field] = cell;
      } else if (typeof cell === 'string') {
        const num = parseNumericValue(cell);
        if (num !== undefined) {
          entry[field] = num;
        } else {
          errors.push(`Row ${i + 1}, column "${headerRow[col]}": could not parse "${cell}"`);
        }
      }
    }

    if (Object.keys(entry).length > 0) {
      parsed.push(entry);
    }
  }

  return { parsed, errors };
}
