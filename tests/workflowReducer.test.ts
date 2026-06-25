import { describe, it, expect } from 'vitest';
import {
  workflowReducer,
  initialWorkflowState,
  type WorkflowState,
  type WorkflowAction,
} from '../src/utils/workflowReducer';
import { mergeAssumptions } from '../src/utils/assumptionEngine';
import type { AssumptionMetadata } from '../src/models/aiTypes';

describe('workflowReducer', () => {
  describe('NEXT', () => {
    it('advances input → assumptions → review → results', () => {
      let state = initialWorkflowState;
      expect(state.step).toBe('input');

      state = workflowReducer(state, { type: 'NEXT' });
      expect(state.step).toBe('assumptions');

      state = workflowReducer(state, { type: 'NEXT' });
      expect(state.step).toBe('review');

      state = workflowReducer(state, { type: 'NEXT' });
      expect(state.step).toBe('results');
    });

    it('clamps at results', () => {
      const state: WorkflowState = { ...initialWorkflowState, step: 'results' };
      const next = workflowReducer(state, { type: 'NEXT' });
      expect(next.step).toBe('results');
    });
  });

  describe('BACK', () => {
    it('goes back and clamps at input', () => {
      let state: WorkflowState = { ...initialWorkflowState, step: 'results' };

      state = workflowReducer(state, { type: 'BACK' });
      expect(state.step).toBe('review');

      state = workflowReducer(state, { type: 'BACK' });
      expect(state.step).toBe('assumptions');

      state = workflowReducer(state, { type: 'BACK' });
      expect(state.step).toBe('input');

      state = workflowReducer(state, { type: 'BACK' });
      expect(state.step).toBe('input');
    });

    it('preserves inputs/metadata/inputText on BACK', () => {
      const metadata: AssumptionMetadata[] = [
        { field: 'revenue', value: 1000, source: 'user-provided', confidence: 'high', rationale: 'test' },
      ];
      const state: WorkflowState = {
        ...initialWorkflowState,
        step: 'review',
        inputs: mergeAssumptions({ revenue: 5000 }),
        metadata,
        inputText: 'hello world',
      };

      const prev = workflowReducer(state, { type: 'BACK' });
      expect(prev.step).toBe('assumptions');
      expect(prev.inputs.revenue).toBe(5000);
      expect(prev.metadata).toBe(metadata);
      expect(prev.inputText).toBe('hello world');
    });
  });

  describe('GOTO_STEP', () => {
    it('allows backward navigation (results → input)', () => {
      const state: WorkflowState = { ...initialWorkflowState, step: 'results' };
      const result = workflowReducer(state, { type: 'GOTO_STEP', step: 'input' });
      expect(result.step).toBe('input');
    });

    it('ignores forward jumps (input → results stays input)', () => {
      const state = initialWorkflowState;
      const result = workflowReducer(state, { type: 'GOTO_STEP', step: 'results' });
      expect(result.step).toBe('input');
    });

    it('ignores same-step navigation', () => {
      const state: WorkflowState = { ...initialWorkflowState, step: 'review' };
      const result = workflowReducer(state, { type: 'GOTO_STEP', step: 'review' });
      expect(result.step).toBe('review');
    });
  });

  describe('RESET', () => {
    it('returns deep-equal to initialWorkflowState', () => {
      const state: WorkflowState = {
        ...initialWorkflowState,
        step: 'results',
        inputText: 'some text',
        inputs: mergeAssumptions({ revenue: 9999 }),
        metadata: [{ field: 'x', value: 1, source: 'ai-inferred', confidence: 'medium', rationale: '' }],
        outputs: { projectedRevenue: [1], projectedFCFF: [1], discountFactors: [1], pvFCFF: [1], terminalValue: 1, pvTerminalValue: 1, enterpriseValue: 1, equityValue: 1, impliedSharePrice: 1, wacc: 0.1 },
      };
      const result = workflowReducer(state, { type: 'RESET' });
      expect(result).toEqual(initialWorkflowState);
    });
  });

  describe('SET_ASSUMPTIONS', () => {
    it('sets metadata and merges inputs via mergeAssumptions', () => {
      const meta: AssumptionMetadata[] = [
        { field: 'revenue', value: 2000, source: 'ai-inferred', confidence: 'medium', rationale: 'parsed' },
      ];
      const result = workflowReducer(initialWorkflowState, {
        type: 'SET_ASSUMPTIONS',
        inputs: { revenue: 2000 },
        metadata: meta,
      });
      expect(result.inputs.revenue).toBe(2000);
      expect(result.metadata).toBe(meta);
      // mergeAssumptions preserves defaults for unset fields
      expect(result.inputs.projectionYears).toBe(initialWorkflowState.inputs.projectionYears);
    });
  });

  describe('SET_FIELD', () => {
    it('updates a flat field', () => {
      const result = workflowReducer(initialWorkflowState, {
        type: 'SET_FIELD',
        field: 'revenue',
        value: 5000,
      });
      expect(result.inputs.revenue).toBe(5000);
    });

    it('updates a company. field', () => {
      const result = workflowReducer(initialWorkflowState, {
        type: 'SET_FIELD',
        field: 'company.companyName',
        value: 'Acme Corp',
      });
      expect(result.inputs.company.companyName).toBe('Acme Corp');
    });
  });

  describe('SET_INPUT_MODE', () => {
    it('updates inputMode', () => {
      const result = workflowReducer(initialWorkflowState, {
        type: 'SET_INPUT_MODE',
        mode: 'structured',
      });
      expect(result.inputMode).toBe('structured');
    });
  });

  describe('SET_INPUT_TEXT', () => {
    it('updates inputText', () => {
      const result = workflowReducer(initialWorkflowState, {
        type: 'SET_INPUT_TEXT',
        text: 'Revenue is 5B',
      });
      expect(result.inputText).toBe('Revenue is 5B');
    });
  });

  describe('SET_OUTPUTS', () => {
    it('stores DCFOutputs', () => {
      const outputs = {
        projectedRevenue: [100],
        projectedFCFF: [50],
        discountFactors: [0.9],
        pvFCFF: [45],
        terminalValue: 500,
        pvTerminalValue: 400,
        enterpriseValue: 445,
        equityValue: 445,
        impliedSharePrice: 44.5,
        wacc: 0.1,
      };
      const result = workflowReducer(initialWorkflowState, {
        type: 'SET_OUTPUTS',
        outputs,
      });
      expect(result.outputs).toBe(outputs);
    });

    it('stores null', () => {
      const state: WorkflowState = {
        ...initialWorkflowState,
        outputs: { projectedRevenue: [1], projectedFCFF: [1], discountFactors: [1], pvFCFF: [1], terminalValue: 1, pvTerminalValue: 1, enterpriseValue: 1, equityValue: 1, impliedSharePrice: 1, wacc: 0.1 },
      };
      const result = workflowReducer(state, { type: 'SET_OUTPUTS', outputs: null });
      expect(result.outputs).toBeNull();
    });
  });

  describe('EXPRESS', () => {
    it('jumps to results step', () => {
      const state: WorkflowState = { ...initialWorkflowState, step: 'assumptions' };
      const result = workflowReducer(state, { type: 'EXPRESS' });
      expect(result.step).toBe('results');
    });
  });
});
