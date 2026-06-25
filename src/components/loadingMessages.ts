export type LoadingStage = 'parsing' | 'market-data' | 'generating';

export const LOADING_STAGES: LoadingStage[] = ['parsing', 'market-data', 'generating'];

const STAGE_MESSAGES: Record<LoadingStage, string> = {
  'parsing': 'Parsing your description...',
  'market-data': 'Retrieving market data...',
  'generating': 'Generating assumptions...',
};

export function loadingStageMessage(stage: LoadingStage): string {
  return STAGE_MESSAGES[stage];
}
