import { useState, useMemo } from 'react'
import Disclaimer from './components/Disclaimer'
import TextInputPanel from './components/TextInputPanel'
import AssumptionsForm from './components/AssumptionsForm'
import DcfOutputTable from './components/DcfOutputTable'
import SensitivityTable from './components/SensitivityTable'
import FollowUpQuestions from './components/FollowUpQuestions'
import { mergeAssumptions } from './utils/assumptionEngine'
import { runFullDCF } from './utils/dcfCalculations'
import { validateInputs, validateOutputs } from './utils/validation'
import type { DCFInputs, DCFOutputs, FinancialData, ValidationWarning } from './models/financialTypes'

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
type EntryMode = 'manual' | 'paste'

function App() {
  const [view, setView] = useState<View>('landing')
  const [mode, setMode] = useState<EntryMode>('manual')
  const [inputs, setInputs] = useState<DCFInputs>(() => mergeAssumptions({}))
  const [hasPasted, setHasPasted] = useState(false)

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

  function handleFieldChange(field: string, value: number | string) {
    setInputs((prev) => {
      if (field.startsWith('company.')) {
        const companyKey = field.slice(8);
        return { ...prev, company: { ...prev.company, [companyKey]: value } }
      }
      return { ...prev, [field]: value }
    })
  }

  if (view === 'workspace') {
    return (
      <div className="min-h-screen p-8">
        <h1 className="text-3xl font-bold mb-6">DCF Workspace</h1>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div>
            {mode === 'paste' && <TextInputPanel onParsed={handleParsed} />}
            <AssumptionsForm values={inputs} onChange={handleFieldChange} />
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
              <div className="space-y-8">
                <Disclaimer />
                <DcfOutputTable outputs={outputs} inputs={inputs} />
                <SensitivityTable inputs={inputs} />
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
        </div>
      </div>
    </div>
  )
}

export default App
