import type { DCFInputs, DCFOutputs } from '../models/financialTypes';
import type { AssumptionMetadata, WorkflowStep } from '../models/aiTypes';
import { mergeAssumptions } from './assumptionEngine';

/** Input mode for Step 1. */
export type InputMode = 'nl' | 'structured' | 'file';

/** Concrete state for the 4-step workflow (ITEM-030). */
export interface WorkflowState {
  step: WorkflowStep;
  inputs: DCFInputs;
  metadata: AssumptionMetadata[];
  inputText: string;
  inputMode: InputMode;
  outputs: DCFOutputs | null;
}

/** Discriminated-union actions for the workflow reducer. */
export type WorkflowAction =
  | { type: 'GOTO_STEP'; step: WorkflowStep }
  | { type: 'NEXT' }
  | { type: 'BACK' }
  | { type: 'RESET' }
  | { type: 'SET_INPUT_TEXT'; text: string }
  | { type: 'SET_INPUT_MODE'; mode: InputMode }
  | { type: 'SET_ASSUMPTIONS'; inputs: Partial<DCFInputs>; metadata: AssumptionMetadata[] }
  | { type: 'SET_FIELD'; field: string; value: number | string }
  | { type: 'SET_OUTPUTS'; outputs: DCFOutputs | null }
  | { type: 'EXPRESS' };

const STEP_ORDER: WorkflowStep[] = ['input', 'assumptions', 'review', 'results'];

export const initialWorkflowState: WorkflowState = {
  step: 'input',
  inputs: mergeAssumptions({}),
  metadata: [],
  inputText: '',
  inputMode: 'nl',
  outputs: null,
};

function stepIndex(step: WorkflowStep): number {
  return STEP_ORDER.indexOf(step);
}

export function workflowReducer(state: WorkflowState, action: WorkflowAction): WorkflowState {
  switch (action.type) {
    case 'NEXT': {
      const idx = stepIndex(state.step);
      const next = Math.min(idx + 1, STEP_ORDER.length - 1);
      return { ...state, step: STEP_ORDER[next] };
    }
    case 'BACK': {
      const idx = stepIndex(state.step);
      const prev = Math.max(idx - 1, 0);
      return { ...state, step: STEP_ORDER[prev] };
    }
    case 'GOTO_STEP': {
      const targetIdx = stepIndex(action.step);
      const currentIdx = stepIndex(state.step);
      // Backward-only: ignore forward jumps
      if (targetIdx >= currentIdx) return state;
      return { ...state, step: action.step };
    }
    case 'RESET':
      return initialWorkflowState;
    case 'SET_INPUT_TEXT':
      return { ...state, inputText: action.text };
    case 'SET_INPUT_MODE':
      return { ...state, inputMode: action.mode };
    case 'SET_ASSUMPTIONS':
      return {
        ...state,
        inputs: mergeAssumptions({ ...state.inputs, ...action.inputs }),
        metadata: action.metadata,
      };
    case 'SET_FIELD': {
      if (action.field.startsWith('company.')) {
        const companyKey = action.field.slice(8);
        return {
          ...state,
          inputs: { ...state.inputs, company: { ...state.inputs.company, [companyKey]: action.value } },
        };
      }
      return { ...state, inputs: { ...state.inputs, [action.field]: action.value } };
    }
    case 'SET_OUTPUTS':
      return { ...state, outputs: action.outputs };
    case 'EXPRESS':
      return { ...state, step: 'results' };
    default:
      return state;
  }
}
