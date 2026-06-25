import { useState, lazy, Suspense } from 'react';
import DcfOutputTable from './DcfOutputTable';
import SensitivityTable from './SensitivityTable';
import Comparables from './Comparables';
import Disclaimer from './Disclaimer';
import { probabilityWeightedScenarios } from '../utils/assumptionEngine';
import { generateCSV, downloadCSV } from '../utils/exportResults';
import type { DCFInputs, DCFOutputs } from '../models/financialTypes';
import type { WorkflowAction } from '../utils/workflowReducer';

const Charts = lazy(() => import('./Charts'));

type OutputTab = 'valuation' | 'charts' | 'comparables';

interface ResultsStepProps {
  inputs: DCFInputs;
  outputs: DCFOutputs;
  dispatch: React.Dispatch<WorkflowAction>;
}

export default function ResultsStep({ inputs, outputs, dispatch }: ResultsStepProps) {
  const [outputTab, setOutputTab] = useState<OutputTab>('valuation');
  const [weights, setWeights] = useState({ conservative: 0.25, base: 0.5, optimistic: 0.25 });
  const [exportStatus, setExportStatus] = useState<'idle' | 'clipboard' | 'failed'>('idle');

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold">Step 4: Valuation Results</h2>

      {/* Actions at top */}
      <div className="flex gap-3">
        <button
          type="button"
          onClick={() => dispatch({ type: 'GOTO_STEP', step: 'review' })}
          className="px-4 py-2 border border-gray-300 text-gray-700 font-medium rounded hover:bg-gray-50 transition-colors"
        >
          ← Edit Assumptions
        </button>
        <button
          type="button"
          onClick={() => dispatch({ type: 'RESET' })}
          className="px-4 py-2 border border-red-300 text-red-700 font-medium rounded hover:bg-red-50 transition-colors"
        >
          Start Over
        </button>
      </div>

      {/* Tab strip */}
      <div className="flex border-b border-gray-300">
        {(['valuation', 'charts', 'comparables'] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setOutputTab(tab)}
            className={`px-4 py-2 text-sm font-medium capitalize ${
              outputTab === tab
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Valuation tab */}
      {outputTab === 'valuation' && (
        <div className="space-y-8">
          <Disclaimer />
          <DcfOutputTable outputs={outputs} inputs={inputs} />
          <SensitivityTable inputs={inputs} />

          {/* Probability-weighted scenarios */}
          <div>
            <h3 className="text-lg font-semibold mb-2">Probability-Weighted Scenarios</h3>
            <div className="flex gap-4 mb-3">
              {(['conservative', 'base', 'optimistic'] as const).map((s) => (
                <label key={s} className="text-sm capitalize">
                  {s}:
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={weights[s]}
                    onChange={(e) => setWeights((w) => ({ ...w, [s]: parseFloat(e.target.value) || 0 }))}
                    className="ml-1 w-16 border rounded px-2 py-1 text-sm"
                  />
                </label>
              ))}
            </div>
            {(() => {
              const result = probabilityWeightedScenarios(inputs, weights);
              const fmtP = (n: number | null) =>
                n === null ? 'N/A' : n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
              return (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                  <div className="p-3 bg-gray-50 rounded border"><div className="text-gray-500">Conservative</div><div className="font-semibold">{fmtP(result.conservative)}</div></div>
                  <div className="p-3 bg-gray-50 rounded border"><div className="text-gray-500">Base</div><div className="font-semibold">{fmtP(result.base)}</div></div>
                  <div className="p-3 bg-gray-50 rounded border"><div className="text-gray-500">Optimistic</div><div className="font-semibold">{fmtP(result.optimistic)}</div></div>
                  <div className="p-3 bg-blue-50 rounded border border-blue-200"><div className="text-blue-600">Weighted Price</div><div className="font-bold">{fmtP(result.weighted)}</div></div>
                </div>
              );
            })()}
          </div>

          {/* Download CSV button */}
          <button
            type="button"
            onClick={async () => {
              const status = await downloadCSV('dcf-results.csv', generateCSV(inputs, outputs));
              setExportStatus(status === 'downloaded' ? 'idle' : status);
            }}
            className="px-4 py-2 bg-gray-800 text-white text-sm font-medium rounded hover:bg-gray-900 transition-colors"
          >
            Download Results
          </button>
          {exportStatus !== 'idle' && (
            <p className="text-red-600 text-sm mt-2">
              Export failed. Please try again or copy the data from the table directly.
              {exportStatus === 'clipboard' && (
                <span className="block text-gray-600">The results have been copied to your clipboard instead.</span>
              )}
            </p>
          )}
        </div>
      )}

      {/* Charts tab (lazy-loaded) */}
      {outputTab === 'charts' && (
        <Suspense fallback={<div className="text-sm text-gray-500 py-8 text-center">Loading charts…</div>}>
          <Charts inputs={inputs} outputs={outputs} />
        </Suspense>
      )}

      {/* Comparables tab */}
      {outputTab === 'comparables' && (
        <Comparables inputs={inputs} outputs={outputs} />
      )}
    </div>
  );
}
