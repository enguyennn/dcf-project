import AssumptionsForm from './AssumptionsForm';
import FollowUpQuestions from './FollowUpQuestions';
import type { DCFInputs, FinancialData, ValidationWarning } from '../models/financialTypes';
import type { InputMode, WorkflowAction } from '../utils/workflowReducer';

const REQUIRED_FIELDS: (keyof FinancialData)[] = ['revenue', 'sharesOutstanding'];

interface ReviewStepProps {
  inputs: DCFInputs;
  inputMode: InputMode;
  warnings: ValidationWarning[];
  dispatch: React.Dispatch<WorkflowAction>;
  onCalculate: () => void;
}

export default function ReviewStep({ inputs, inputMode, warnings, dispatch, onCalculate }: ReviewStepProps) {
  const missingFields = REQUIRED_FIELDS.filter((f) => (inputs[f] ?? 0) <= 0);

  function handleFieldChange(field: string, value: number | string) {
    dispatch({ type: 'SET_FIELD', field, value });
  }

  function handleBack() {
    // If entered via structured/file path, go back to input (skip AI Assumptions)
    if (inputMode === 'structured' || inputMode === 'file') {
      dispatch({ type: 'GOTO_STEP', step: 'input' });
    } else {
      dispatch({ type: 'BACK' });
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold">Step 3: Review & Edit Assumptions</h2>
      <p className="text-gray-600">
        Fine-tune all assumptions before running the DCF calculation.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div>
          <AssumptionsForm values={inputs} onChange={handleFieldChange} />
        </div>
        <div className="space-y-4">
          {missingFields.length > 0 && (
            <FollowUpQuestions
              missingFields={missingFields}
              onFieldSubmit={(field, value) => handleFieldChange(field, value)}
            />
          )}

          {/* Warnings */}
          {warnings.length > 0 && (
            <div className="space-y-1">
              {warnings.map((w, i) => (
                <div
                  key={i}
                  className={`px-3 py-2 rounded text-sm border ${
                    w.severity === 'error'
                      ? 'border-red-400 bg-red-50 text-red-800'
                      : 'border-yellow-400 bg-yellow-50 text-yellow-800'
                  }`}
                >
                  <span className="font-medium">{w.field}:</span> {w.message}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3 pt-4">
        <button
          type="button"
          onClick={handleBack}
          className="px-4 py-2 border border-gray-300 text-gray-700 font-medium rounded hover:bg-gray-50 transition-colors"
        >
          ← Back
        </button>
        <button
          type="button"
          onClick={onCalculate}
          className="px-6 py-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 transition-colors"
        >
          Calculate DCF
        </button>
      </div>
    </div>
  );
}
