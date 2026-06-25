import { describe, it, expect } from 'vitest';
import { loadingStageMessage, LOADING_STAGES, type LoadingStage } from '../src/components/loadingMessages';

describe('loadingMessages', () => {
  it('maps "parsing" to exact PRD string', () => {
    expect(loadingStageMessage('parsing')).toBe('Parsing your description...');
  });

  it('maps "market-data" to exact PRD string', () => {
    expect(loadingStageMessage('market-data')).toBe('Retrieving market data...');
  });

  it('maps "generating" to exact PRD string', () => {
    expect(loadingStageMessage('generating')).toBe('Generating assumptions...');
  });

  it('LOADING_STAGES contains all 3 stages', () => {
    expect(LOADING_STAGES).toEqual(['parsing', 'market-data', 'generating']);
  });

  it('every stage in LOADING_STAGES maps to a non-empty string', () => {
    for (const stage of LOADING_STAGES) {
      const msg = loadingStageMessage(stage);
      expect(msg).toBeTruthy();
      expect(typeof msg).toBe('string');
    }
  });
});
