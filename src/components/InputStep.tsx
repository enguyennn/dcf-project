import { useState } from 'react';
import FileUpload from './FileUpload';
import LoadingState from './LoadingState';
import { hybridParse } from '../utils/hybridParser';
import type { DCFInputs, FinancialData } from '../models/financialTypes';
import type { AssumptionMetadata } from '../models/aiTypes';
import type { InputMode, WorkflowAction } from '../utils/workflowReducer';

interface InputStepProps {
  inputText: string;
  inputMode: InputMode;
  dispatch: React.Dispatch<WorkflowAction>;
}

export default function InputStep({ inputText, inputMode, dispatch }: InputStepProps) {
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  async function handleSubmit() {
    if (inputMode === 'file') return; // file handled via FileUpload callback
    const text = inputText.trim();
    if (!text) return;

    setLoading(true);
    setErrors([]);

    const result = await hybridParse(text);
    setLoading(false);

    if (result.errors.length > 0) {
      setErrors(result.errors);
    }

    dispatch({ type: 'SET_ASSUMPTIONS', inputs: result.parsed, metadata: result.metadata });

    // Route: structured input (all user-provided) → skip AI Assumptions, go to Review
    const allUserProvided = result.metadata.length > 0 && result.metadata.every(m => m.source === 'user-provided');
    if (inputMode === 'structured' || allUserProvided) {
      // NEXT twice: input → assumptions → review
      dispatch({ type: 'NEXT' }); // → assumptions
      dispatch({ type: 'NEXT' }); // → review
    } else {
      dispatch({ type: 'NEXT' }); // → assumptions (NL path)
    }
  }

  function handleFileParsed(rows: Partial<FinancialData>[]) {
    if (rows.length === 0) return;
    const parsed: Partial<DCFInputs> = rows[0];
    const metadata: AssumptionMetadata[] = Object.entries(parsed).map(([field, value]) => ({
      field,
      value: value as number,
      source: 'user-provided' as const,
      confidence: 'high' as const,
      rationale: 'Parsed from uploaded file',
    }));
    dispatch({ type: 'SET_ASSUMPTIONS', inputs: parsed, metadata });
    // File upload → structured path → skip to Review
    dispatch({ type: 'NEXT' }); // → assumptions
    dispatch({ type: 'NEXT' }); // → review
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold">Step 1: Enter Financial Data</h2>
      <p className="text-gray-600">
        Describe the company in natural language, paste structured data, or upload a file.
      </p>

      {/* Mode tabs */}
      <div className="flex flex-wrap border-b border-gray-300">
        {([
          { key: 'nl' as const, label: 'Natural Language' },
          { key: 'structured' as const, label: 'Structured Data' },
          { key: 'file' as const, label: 'File Upload' },
        ]).map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => dispatch({ type: 'SET_INPUT_MODE', mode: key })}
            className={`px-4 py-2 text-sm font-medium ${
              inputMode === key
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Input area */}
      {inputMode !== 'file' ? (
        <div className="space-y-3">
          <textarea
            value={inputText}
            onChange={(e) => dispatch({ type: 'SET_INPUT_TEXT', text: e.target.value })}
            placeholder={
              inputMode === 'nl'
                ? 'e.g. "Apple has $400B revenue growing at 8%, 30% operating margins, trades at $190 with 15.3B shares..."'
                : 'Revenue: 400,000,000,000\nOperating Income: 120,000,000,000\nShares Outstanding: 15.3B'
            }
            className="w-full min-h-40 font-mono border border-gray-300 rounded p-3 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            disabled={loading}
          />
          <button
            type="button"
            onClick={handleSubmit}
            disabled={loading || !inputText.trim()}
            className="px-6 py-2 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Continue
          </button>
          {loading && <LoadingState stage="generating" />}
        </div>
      ) : (
        <FileUpload onParsed={handleFileParsed} />
      )}

      {/* Errors */}
      {errors.length > 0 && (
        <div className="space-y-1">
          {errors.map((err, i) => (
            <p key={i} className="text-red-600 text-sm">{err}</p>
          ))}
        </div>
      )}
    </div>
  );
}
