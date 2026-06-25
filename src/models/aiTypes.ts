import type { DCFInputs, ResearchDataSource } from './financialTypes';

/** Indicates how an assumption value was sourced. */
export type AssumptionSource =
  | 'industry-benchmark'
  | 'ai-inferred'
  | 'market-data'
  | 'user-provided'
  | 'default';

/** Metadata for a single assumption field produced by the AI parse pipeline. */
export interface AssumptionMetadata {
  field: string;
  value: number;
  source: AssumptionSource;
  confidence: 'high' | 'medium' | 'low';
  rationale: string;
}

/** Steps in the 4-step AI-assisted workflow. */
export type WorkflowStep = 'input' | 'assumptions' | 'review' | 'results';

/** State machine for the AI workflow. */
export interface WorkflowState {
  step: WorkflowStep;
  inputText: string;
  parsedAssumptions: Partial<DCFInputs> | null;
  metadata: AssumptionMetadata[];
  warnings: string[];
}

/** Discriminated-union actions for the workflow reducer. */
export type WorkflowAction =
  | { type: 'GOTO_STEP'; step: WorkflowStep }
  | { type: 'NEXT' }
  | { type: 'BACK' }
  | { type: 'RESET' }
  | { type: 'SET_INPUT'; text: string }
  | { type: 'SET_ASSUMPTIONS'; assumptions: Partial<DCFInputs>; metadata: AssumptionMetadata[] };

/** Response from the AI parse endpoint. */
export interface ParseResponse {
  assumptions: Partial<DCFInputs>;
  metadata: AssumptionMetadata[];
  followUp?: string[];
}

/** Response from the market data endpoint. */
export interface MarketDataResponse {
  data: {
    beta?: ResearchDataSource;
    riskFreeRate?: ResearchDataSource;
    equityRiskPremium?: ResearchDataSource;
  };
  errors: string[];
}

/** Industry-level benchmark assumptions. All rates are decimals (e.g. 0.05 = 5%). */
export interface IndustryBenchmark {
  industry: string;
  aliases: string[];
  revenueGrowthRate: number;
  operatingMarginRate: number;
  dAndARate: number;
  capExRate: number;
  nwcRate: number;
  costOfDebt: number;
  betaRange: { low: number; mid: number; high: number };
}
