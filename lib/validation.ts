export function validateParseInput(
  body: unknown
): { valid: true; text: string; industry?: string } | { valid: false; error: string } {
  if (body === null || typeof body !== 'object') {
    return { valid: false, error: 'Request body must be a JSON object' };
  }

  const obj = body as Record<string, unknown>;

  if (typeof obj.text !== 'string') {
    return { valid: false, error: 'Field "text" is required and must be a string' };
  }

  const trimmed = obj.text.trim();

  if (trimmed.length === 0) {
    return { valid: false, error: 'Field "text" must not be empty' };
  }

  if (trimmed.length > 2000) {
    return { valid: false, error: 'Field "text" must be at most 2000 characters' };
  }

  const result: { valid: true; text: string; industry?: string } = { valid: true, text: trimmed };

  if (obj.industry !== undefined) {
    if (typeof obj.industry === 'string') {
      result.industry = obj.industry;
    }
  }

  return result;
}

export function validateTickerInput(
  query: unknown
): { valid: true; ticker: string } | { valid: false; error: string } {
  if (query === null || typeof query !== 'object') {
    return { valid: false, error: 'Query must be a JSON object' };
  }

  const obj = query as Record<string, unknown>;

  if (typeof obj.ticker !== 'string') {
    return { valid: false, error: 'Field "ticker" is required and must be a string' };
  }

  const ticker = obj.ticker.trim();

  if (ticker.length === 0) {
    return { valid: false, error: 'Field "ticker" must not be empty' };
  }

  if (ticker.length > 10) {
    return { valid: false, error: 'Field "ticker" must be at most 10 characters' };
  }

  if (!/^[a-zA-Z0-9]+$/.test(ticker)) {
    return { valid: false, error: 'Field "ticker" must be alphanumeric' };
  }

  return { valid: true, ticker: ticker.toUpperCase() };
}
