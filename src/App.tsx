import { useState } from 'react'
import Disclaimer from './components/Disclaimer'
import TextInputPanel from './components/TextInputPanel'
import AssumptionsForm from './components/AssumptionsForm'
import { mergeAssumptions } from './utils/assumptionEngine'
import type { DCFInputs, FinancialData } from './models/financialTypes'

type View = 'landing' | 'workspace'
type EntryMode = 'manual' | 'paste'

function App() {
  const [view, setView] = useState<View>('landing')
  const [mode, setMode] = useState<EntryMode>('manual')
  const [inputs, setInputs] = useState<DCFInputs>(() => mergeAssumptions({}))

  function handleStart(selectedMode: EntryMode) {
    setMode(selectedMode)
    setView('workspace')
  }

  function handleParsed(parsed: Partial<FinancialData>) {
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
          <div className="text-sm text-gray-500">
            <p>Entry mode: <span className="font-semibold">{mode}</span></p>
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
