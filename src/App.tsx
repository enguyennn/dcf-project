import { useState } from 'react'
import Disclaimer from './components/Disclaimer'

type View = 'landing' | 'workspace'
type EntryMode = 'manual' | 'paste'

function App() {
  const [view, setView] = useState<View>('landing')
  const [mode, setMode] = useState<EntryMode>('manual')

  function handleStart(selectedMode: EntryMode) {
    setMode(selectedMode)
    setView('workspace')
  }

  if (view === 'workspace') {
    return (
      <div className="min-h-screen flex items-center justify-center p-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold mb-4">DCF Workspace</h1>
          <p className="text-gray-600">Entry mode: <span className="font-semibold">{mode}</span></p>
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
