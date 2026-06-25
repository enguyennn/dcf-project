import { useReducer, useMemo } from 'react'
import WorkflowStepIndicator from './components/WorkflowStepIndicator'
import InputStep from './components/InputStep'
import AIAssumptionsStep from './components/AIAssumptionsStep'
import ReviewStep from './components/ReviewStep'
import ResultsStep from './components/ResultsStep'
import { workflowReducer, initialWorkflowState } from './utils/workflowReducer'
import { runFullDCF } from './utils/dcfCalculations'
import { validateInputs, validateOutputs } from './utils/validation'
import type { DCFOutputs, ValidationWarning } from './models/financialTypes'
import type { WorkflowStep } from './models/aiTypes'

function App() {
  const [state, dispatch] = useReducer(workflowReducer, initialWorkflowState)

  const { outputs, warnings, hasBlockingError } = useMemo(() => {
    const inputWarnings: ValidationWarning[] = validateInputs(state.inputs)
    let computedOutputs: DCFOutputs | null = null
    let allWarnings = [...inputWarnings]

    try {
      computedOutputs = runFullDCF(state.inputs)
      const outputWarnings = validateOutputs(computedOutputs)
      allWarnings = [...allWarnings, ...outputWarnings]
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'DCF calculation failed'
      allWarnings.push({ field: 'calculation', message, severity: 'error' })
    }

    const hasBlocking = computedOutputs === null || allWarnings.some((w) => w.severity === 'error')
    return { outputs: computedOutputs, warnings: allWarnings, hasBlockingError: hasBlocking }
  }, [state.inputs])

  function handleCalculate() {
    dispatch({ type: 'SET_OUTPUTS', outputs })
    dispatch({ type: 'NEXT' }) // review → results
  }

  function handleNavigate(step: WorkflowStep) {
    dispatch({ type: 'GOTO_STEP', step })
  }

  return (
    <div className="min-h-screen p-8">
      <h1 className="text-3xl font-bold text-center mb-2">DCF Model Builder</h1>
      <WorkflowStepIndicator currentStep={state.step} onNavigate={handleNavigate} />

      {state.step === 'input' && (
        <InputStep
          inputText={state.inputText}
          inputMode={state.inputMode}
          dispatch={dispatch}
        />
      )}

      {state.step === 'assumptions' && (
        <AIAssumptionsStep
          inputs={state.inputs}
          metadata={state.metadata}
          dispatch={dispatch}
        />
      )}

      {state.step === 'review' && (
        <ReviewStep
          inputs={state.inputs}
          inputMode={state.inputMode}
          warnings={warnings}
          dispatch={dispatch}
          onCalculate={handleCalculate}
        />
      )}

      {state.step === 'results' && !hasBlockingError && outputs && (
        <ResultsStep
          inputs={state.inputs}
          outputs={outputs}
          dispatch={dispatch}
        />
      )}

      {state.step === 'results' && (hasBlockingError || !outputs) && (
        <div className="max-w-2xl mx-auto text-center space-y-4 mt-8">
          <p className="text-red-600 font-medium">
            Cannot display results — there are blocking errors in the assumptions.
          </p>
          {warnings.filter(w => w.severity === 'error').map((w, i) => (
            <div key={i} className="px-3 py-2 rounded text-sm border border-red-400 bg-red-50 text-red-800">
              <span className="font-medium">{w.field}:</span> {w.message}
            </div>
          ))}
          <button
            type="button"
            onClick={() => dispatch({ type: 'GOTO_STEP', step: 'review' })}
            className="px-4 py-2 border border-gray-300 text-gray-700 font-medium rounded hover:bg-gray-50 transition-colors"
          >
            ← Back to Review
          </button>
        </div>
      )}
    </div>
  )
}

export default App
