import SourceBadge from './SourceBadge';
import AssumptionSummary from './AssumptionSummary';
import type { DCFInputs } from '../models/financialTypes';
import type { AssumptionMetadata } from '../models/aiTypes';
import type { WorkflowAction } from '../utils/workflowReducer';

interface AIAssumptionsStepProps {
  inputs: DCFInputs;
  metadata: AssumptionMetadata[];
  dispatch: React.Dispatch<WorkflowAction>;
}

export default function AIAssumptionsStep({ inputs, metadata, dispatch }: AIAssumptionsStepProps) {
  function handleOverride(field: string, value: number) {
    dispatch({ type: 'SET_FIELD', field, value });
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold">Step 2: AI-Extracted Assumptions</h2>
      <p className="text-gray-600">
        Review the assumptions extracted from your input. Override any values before proceeding.
      </p>

      <AssumptionSummary metadata={metadata} />

      {/* Assumption cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {metadata.map((m) => (
          <div key={m.field} className="border border-gray-200 rounded-lg p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">{m.field}</span>
              <SourceBadge source={m.source} rationale={m.rationale} />
            </div>
            <input
              type="number"
              value={(inputs as unknown as Record<string, number>)[m.field] ?? m.value}
              onChange={(e) => handleOverride(m.field, parseFloat(e.target.value) || 0)}
              className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            {m.rationale && (
              <p className="text-xs text-gray-500">{m.rationale}</p>
            )}
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="flex gap-3 pt-4">
        <button
          type="button"
          onClick={() => dispatch({ type: 'BACK' })}
          className="px-4 py-2 border border-gray-300 text-gray-700 font-medium rounded hover:bg-gray-50 transition-colors"
        >
          ← Back
        </button>
        <button
          type="button"
          onClick={() => dispatch({ type: 'NEXT' })}
          className="px-6 py-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 transition-colors"
        >
          Accept & Review
        </button>
        <button
          type="button"
          onClick={() => dispatch({ type: 'EXPRESS' })}
          className="px-4 py-2 bg-green-600 text-white font-medium rounded hover:bg-green-700 transition-colors"
        >
          Express Mode →
        </button>
      </div>
    </div>
  );
}
