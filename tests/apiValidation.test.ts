import { describe, it, expect } from 'vitest';
import { validateParseInput, validateTickerInput } from '../api/lib/validation';

describe('validateParseInput', () => {
  it('accepts valid input with text only', () => {
    const result = validateParseInput({ text: 'Apple Inc financials' });
    expect(result).toEqual({ valid: true, text: 'Apple Inc financials' });
  });

  it('accepts valid input with text and industry', () => {
    const result = validateParseInput({ text: 'Revenue data', industry: 'Technology' });
    expect(result).toEqual({ valid: true, text: 'Revenue data', industry: 'Technology' });
  });

  it('trims whitespace from text', () => {
    const result = validateParseInput({ text: '  hello world  ' });
    expect(result).toEqual({ valid: true, text: 'hello world' });
  });

  it('rejects missing text field', () => {
    const result = validateParseInput({ industry: 'Tech' });
    expect(result).toEqual({ valid: false, error: expect.any(String) });
  });

  it('rejects non-string text', () => {
    const result = validateParseInput({ text: 123 });
    expect(result).toEqual({ valid: false, error: expect.any(String) });
  });

  it('rejects empty/whitespace-only text', () => {
    const result = validateParseInput({ text: '   ' });
    expect(result).toEqual({ valid: false, error: expect.any(String) });
  });

  it('rejects text exceeding 2000 characters', () => {
    const result = validateParseInput({ text: 'a'.repeat(2001) });
    expect(result).toEqual({ valid: false, error: expect.any(String) });
  });

  it('accepts text at exactly 2000 characters', () => {
    const text = 'a'.repeat(2000);
    const result = validateParseInput({ text });
    expect(result).toEqual({ valid: true, text });
  });

  it('rejects non-object body (null)', () => {
    const result = validateParseInput(null);
    expect(result).toEqual({ valid: false, error: expect.any(String) });
  });

  it('rejects non-object body (string)', () => {
    const result = validateParseInput('hello');
    expect(result).toEqual({ valid: false, error: expect.any(String) });
  });
});

describe('validateTickerInput', () => {
  it('accepts valid ticker and normalizes to uppercase', () => {
    const result = validateTickerInput({ ticker: 'aapl' });
    expect(result).toEqual({ valid: true, ticker: 'AAPL' });
  });

  it('accepts already-uppercase ticker', () => {
    const result = validateTickerInput({ ticker: 'MSFT' });
    expect(result).toEqual({ valid: true, ticker: 'MSFT' });
  });

  it('rejects non-alphanumeric ticker', () => {
    const result = validateTickerInput({ ticker: 'AA-PL' });
    expect(result).toEqual({ valid: false, error: expect.any(String) });
  });

  it('rejects empty ticker', () => {
    const result = validateTickerInput({ ticker: '' });
    expect(result).toEqual({ valid: false, error: expect.any(String) });
  });

  it('rejects ticker exceeding 10 characters', () => {
    const result = validateTickerInput({ ticker: 'ABCDEFGHIJK' });
    expect(result).toEqual({ valid: false, error: expect.any(String) });
  });

  it('accepts ticker at exactly 10 characters', () => {
    const result = validateTickerInput({ ticker: 'ABCDEFGHIJ' });
    expect(result).toEqual({ valid: true, ticker: 'ABCDEFGHIJ' });
  });

  it('rejects non-string ticker', () => {
    const result = validateTickerInput({ ticker: 123 });
    expect(result).toEqual({ valid: false, error: expect.any(String) });
  });

  it('rejects missing ticker field', () => {
    const result = validateTickerInput({});
    expect(result).toEqual({ valid: false, error: expect.any(String) });
  });

  it('rejects non-object query (null)', () => {
    const result = validateTickerInput(null);
    expect(result).toEqual({ valid: false, error: expect.any(String) });
  });
});
