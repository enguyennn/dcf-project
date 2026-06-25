import { useState, useMemo, lazy, Suspense } from 'react'
import Disclaimer from './components/Disclaimer'
import TextInputPanel from './components/TextInputPanel'
import FileUpload from './components/FileUpload'
import AssumptionsForm from './components/AssumptionsForm'
import DcfOutputTable from './components/DcfOutputTable'
import SensitivityTable from './components/SensitivityTable'
import Comparables from './components/Comparables'
import FollowUpQuestions from './components/FollowUpQuestions'
import { mergeAssumptions, probabilityWeightedScenarios } from './utils/assumptionEngine'
import { runFullDCF } from './utils/dcfCalculations'
import { generateCSV, downloadCSV } from './utils/exportResults'
import { validateInputs, validateOutputs } from './utils/validation'
import type { DCFInputs, DCFOutputs, FinancialData, ValidationWarning, ResearchDataSource } from './models/financialTypes'

const Charts = lazy(() => import('./components/Charts'))

/**
 * Fields whose zero/negative value genuinely blocks a valid DCF:
 * - sharesOutstanding <= 0 causes runFullDCF to throw (cannot compute share price).
 * - revenue <= 0 produces a degenerate all-zero model (meaningless output).
 *
 * Other FinancialData fields are rate-derived inside runFullDCF (operatingIncome,
 * depreciationAmortization, capitalExpenditures, changeInNWC use their *Rate
 * counterparts) or are legitimately valid at 0 (netDebt = no net debt).
 *
 * Because mergeAssumptions fills all FinancialData numerics with 0, a literal
 * undefined/null check would never fire. We treat <= 0 as "missing".
 */
const REQUIRED_FIELDS: (keyof FinancialData)[] = ['revenue', 'sharesOutstanding']

type View = 'landing' | 'workspace'
type EntryMode = 'manual' | 'paste' | 'upload'
type OutputTab = 'valuation' | 'charts' | 'comparables'

function App() {
  const [view, setView] = useState<View>('landing')
  const [mode, setMode] = useState<EntryMode>('manual')
  const [inputs, setInputs] = useState<DCFInputs>(() => mergeAssumptions({}))
  const [hasPasted, setHasPasted] = useState(false)
  const [researched, setResearched] = useState<Record<string, ResearchDataSource>>({})
  const [outputTab, setOutputTab] = useState<OutputTab>('valuation')
  const [weights, setWeights] = useState({ conservative: 0.25, base: 0.5, optimistic: 0.25 })
  const [exportStatus, setExportStatus] = useState<'idle' | 'clipboard' | 'failed'>('idle')
  const { outputs, warnings, hasBlockingError } = useMemo(() => {
    const inputWarnings: ValidationWarning[] = validateInputs(inputs)
    let computedOutputs: DCFOutputs | null = null
    let allWarnings = [...inputWarnings]

    try {
      computedOutputs = runFullDCF(inputs)
      const outputWarnings = validateOutputs(computedOutputs)
      allWarnings = [...allWarnings, ...outputWarnings]
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'DCF calculation failed'
      allWarnings.push({ field: 'calculation', message, severity: 'error' })
    }

    const hasBlocking = computedOutputs === null || allWarnings.some((w) => w.severity === 'error')
    return { outputs: computedOutputs, warnings: allWarnings, hasBlockingError: hasBlocking }
  }, [inputs])

  const missingFields = REQUIRED_FIELDS.filter((f) => (inputs[f] ?? 0) <= 0)

  function handleStart(selectedMode: EntryMode) {
    setMode(selectedMode)
    setView('workspace')
  }

  function handleParsed(parsed: Partial<FinancialData>) {
    setHasPasted(true)
    setInputs((prev) => mergeAssumptions({ ...prev, ...parsed }))
  }

  function handleExcelParsed(rows: Partial<FinancialData>[]) {
    if (rows.length === 0) return
    setHasPasted(true)
    setInputs((prev) => mergeAssumptions({ ...prev, ...rows[0] }))
  }

  function handleFieldChange(field: string, value: number | string) {
    setInputs((prev) => {
      if (field.startsWith('company.')) {
        const companyKey = field.slice(8);
        return { ...prev, company: { ...prev.company, [companyKey]: value } }
      }
      return { ...prev, [field]: value }
    })
  }



  function handleUseManual(field: string) {
    setResearched((prev) => {
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }

  if (view === 'workspace') {
    return (
      <div className="min-h-screen p-8">
        <h1 className="text-3xl font-bold mb-6">DCF Workspace</h1>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div>
            {mode === 'paste' && <TextInputPanel onParsed={handleParsed} />}
            {mode === 'upload' && <FileUpload onParsed={handleExcelParsed} />}
            <AssumptionsForm values={inputs} onChange={handleFieldChange} researched={researched} onUseManual={handleUseManual} />
          </div>
          <div>
            <p className="text-sm text-gray-500 mb-4">Entry mode: <span className="font-semibold">{mode}</span></p>
            {hasPasted && missingFields.length > 0 && (
              <FollowUpQuestions
                missingFields={missingFields}
                onFieldSubmit={(field, value) => handleFieldChange(field, value)}
              />
            )}
            {warnings.length > 0 && (
              <div className="mb-4 space-y-1">
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
            {!hasBlockingError && outputs && (
              <div className="space-y-4">
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

                    {/* Probability-weighted scenarios (ITEM-062) */}
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
                        const result = probabilityWeightedScenarios(inputs, weights)
                        const fmtP = (n: number | null) =>
                          n === null ? 'N/A' : n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                        return (
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                            <div className="p-3 bg-gray-50 rounded border"><div className="text-gray-500">Conservative</div><div className="font-semibold">{fmtP(result.conservative)}</div></div>
                            <div className="p-3 bg-gray-50 rounded border"><div className="text-gray-500">Base</div><div className="font-semibold">{fmtP(result.base)}</div></div>
                            <div className="p-3 bg-gray-50 rounded border"><div className="text-gray-500">Optimistic</div><div className="font-semibold">{fmtP(result.optimistic)}</div></div>
                            <div className="p-3 bg-blue-50 rounded border border-blue-200"><div className="text-blue-600">Weighted Price</div><div className="font-bold">{fmtP(result.weighted)}</div></div>
                          </div>
                        )
                      })()}
                    </div>

                    {/* Download CSV button (ITEM-063) */}
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
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <div className="max-w-2xl w-full space-y-8 text-center">
        <h1 className="text-4xl font-bold">DCF Model Builder</h1>
        <p className="text-gray-700 text-lg">
          A Discounted Cash Flow (DCF) model estimates the intrinsic value of a company
          by projecting future free cash flows and discounting them back to present value.
          Build your own model by entering assumptions or pasting financial data.
        </p>
        <Disclaimer />
        <div className="flex justify-center gap-4">
          <button
            type="button"
            onClick={() => handleStart('manual')}
            className="px-6 py-3 bg-blue-600 text-white font-medium rounded hover:bg-blue-700 transition-colors"
          >
            Enter Assumptions Manually
          </button>
          <button
            type="button"
            onClick={() => handleStart('paste')}
            className="px-6 py-3 bg-green-600 text-white font-medium rounded hover:bg-green-700 transition-colors"
          >
            Paste Financial Data
          </button>
          <button
            type="button"
            onClick={() => handleStart('upload')}
            className="px-6 py-3 bg-purple-600 text-white font-medium rounded hover:bg-purple-700 transition-colors"
          >
            Upload Excel File
          </button>
        </div>
      </div>
    </div>
  )
}

export default App
