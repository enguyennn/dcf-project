import type { DCFInputs, ResearchDataSource, AssumptionSource } from './financialTypes';

// Re-export AssumptionSource so existing consumers of aiTypes keep working.
export type { AssumptionSource } from './financialTypes';

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

// Canonical WorkflowState and WorkflowAction are defined in src/utils/workflowReducer.ts.
// Re-export them here so existing imports from aiTypes continue to work.
export type { WorkflowState, WorkflowAction } from '../utils/workflowReducer';

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
