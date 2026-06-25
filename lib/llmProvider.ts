import OpenAI from 'openai';
import type { ParseResponse, AssumptionMetadata } from '../src/models/aiTypes';
import type { DCFInputs } from '../src/models/financialTypes';

/** Minimal structural type matching the OpenAI SDK's chat.completions.create call. */
export interface OpenAILike {
  chat: {
    completions: {
      create(body: Record<string, unknown>): Promise<{
        choices: Array<{
          message: {
            tool_calls?: Array<{
              function: {
                arguments: string;
              };
            }>;
          };
        }>;
      }>;
    };
  };
}

export interface LLMProvider {
  parseFinancialText(text: string, industry?: string): Promise<ParseResponse>;
}

const SYSTEM_PROMPT = `You are a financial analyst. Extract financial assumptions from the user's text.
Return ALL rates as DECIMALS (e.g., 30% → 0.30, 70% → 0.70, 21% → 0.21).
Revenue should be in absolute dollars (e.g., $50 million → 50000000).
Beta is a unitless number (typically 0.5–2.5).
Only extract values that are explicitly stated or clearly implied in the text.
Use the extract_financial_data tool to return your findings.`;

const EXTRACTION_TOOL = {
  type: 'function' as const,
  function: {
    name: 'extract_financial_data',
    description: 'Extract financial assumptions from the given text.',
    parameters: {
      type: 'object',
      properties: {
        revenue: { type: 'number', description: 'Annual revenue in dollars' },
        revenueGrowthRate: { type: 'number', description: 'Revenue growth rate as a decimal (e.g. 0.30 for 30%)' },
        operatingMarginRate: { type: 'number', description: 'Operating margin rate as a decimal (e.g. 0.20 for 20%)' },
        industry: { type: 'string', description: 'Industry classification (e.g. SaaS, Healthcare, Retail)' },
        dAndARate: { type: 'number', description: 'Depreciation & amortization as a fraction of revenue (decimal)' },
        capExRate: { type: 'number', description: 'Capital expenditures as a fraction of revenue (decimal)' },
        nwcRate: { type: 'number', description: 'Net working capital as a fraction of revenue (decimal)' },
        taxRate: { type: 'number', description: 'Tax rate as a decimal (e.g. 0.21 for 21%)' },
        beta: { type: 'number', description: 'Equity beta (unitless, typically 0.5–2.5)' },
      },
      required: [],
    },
  },
};

/** Numeric fields extracted by the tool, mapped flat onto DCFInputs. */
const NUMERIC_FIELDS = [
  'revenue',
  'revenueGrowthRate',
  'operatingMarginRate',
  'dAndARate',
  'capExRate',
  'nwcRate',
  'taxRate',
  'beta',
] as const;

export class OpenAIProvider implements LLMProvider {
  private client: OpenAILike;

  constructor(client?: OpenAILike) {
    this.client =
      client ?? (new OpenAI({ apiKey: process.env.OPENAI_API_KEY }) as unknown as OpenAILike);
  }

  async parseFinancialText(text: string, industry?: string): Promise<ParseResponse> {
    const userMessage = industry ? `Industry context: ${industry}\n\n${text}` : text;

    const response = await this.client.chat.completions.create({
      model: 'gpt-4o-mini',
      temperature: 0,
      messages: [
        { role: 'system', content: SYSTEM_PROMPT },
        { role: 'user', content: userMessage },
      ],
      tools: [EXTRACTION_TOOL],
      tool_choice: { type: 'function', function: { name: 'extract_financial_data' } },
    });

    const toolCall = response.choices[0]?.message?.tool_calls?.[0];
    if (!toolCall) {
      return { assumptions: {}, metadata: [] };
    }

    const parsed: Record<string, unknown> = JSON.parse(toolCall.function.arguments);

    const assumptions: Partial<DCFInputs> = {};
    const metadata: AssumptionMetadata[] = [];

    for (const field of NUMERIC_FIELDS) {
      const val = parsed[field];
      if (typeof val === 'number' && Number.isFinite(val)) {
        (assumptions as Record<string, number>)[field] = val;
        metadata.push({
          field,
          value: val,
          source: 'ai-inferred',
          confidence: 'medium',
          rationale: 'Extracted from input text',
        });
      }
    }

    // Map industry → company.industry
    if (typeof parsed.industry === 'string' && parsed.industry.trim() !== '') {
      assumptions.company = {
        companyName: '',
        currency: 'USD',
        industry: parsed.industry.trim(),
      };
      metadata.push({
        field: 'company.industry',
        value: 0,
        source: 'ai-inferred',
        confidence: 'medium',
        rationale: `Industry classified as "${parsed.industry}"`,
      });
    }

    return { assumptions, metadata };
  }
}
