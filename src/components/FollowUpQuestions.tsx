import { useState } from 'react'

interface FollowUpQuestionsProps {
  missingFields: string[]
  onFieldSubmit: (field: string, value: number) => void
}

/**
 * Descriptions for FinancialData fields that may be flagged as "missing"
 * (i.e., still at the 0 placeholder after paste parsing).
 *
 * Only fields passed in `missingFields` are rendered; the map is kept broader
 * for completeness in case REQUIRED_FIELDS expands later.
 */
const FIELD_DESCRIPTIONS: Record<string, string> = {
  revenue: 'Total annual revenue (sales). Required to project future cash flows — a zero value produces a degenerate all-zero model.',
  sharesOutstanding: 'Total diluted shares outstanding. Required to compute implied share price — a zero or negative value makes the calculation impossible.',
  netDebt: 'Net debt (total debt minus cash). Used to bridge from enterprise value to equity value.',
  operatingIncome: 'Operating income (EBIT). Used as the base for free cash flow before applying margin rates.',
}

function FollowUpQuestions({ missingFields, onFieldSubmit }: FollowUpQuestionsProps) {
  const [values, setValues] = useState<Record<string, string>>({})

  function handleChange(field: string, input: string) {
    setValues((prev) => ({ ...prev, [field]: input }))
  }

  function handleSubmitAll() {
    for (const field of missingFields) {
      const raw = values[field]
      if (raw === undefined || raw.trim() === '') continue
      const num = Number(raw)
      if (Number.isNaN(num)) continue
      onFieldSubmit(field, num)
    }
  }

  return (
    <div className="border border-blue-300 bg-blue-50 rounded-lg p-4 mb-4">
      <h3 className="text-lg font-semibold text-blue-900 mb-2">
        Follow-Up: Missing Required Fields
      </h3>
      <p className="text-sm text-blue-800 mb-3">
        The following fields could not be extracted from your pasted data. Please provide values to generate a valid DCF model.
      </p>
      <div className="space-y-3">
        {missingFields.map((field) => (
          <div key={field}>
            <label className="block text-sm font-medium text-blue-900 mb-1" htmlFor={`followup-${field}`}>
              {field}
            </label>
            <p className="text-xs text-blue-700 mb-1">
              {FIELD_DESCRIPTIONS[field] ?? 'Provide a numeric value for this field.'}
            </p>
            <input
              id={`followup-${field}`}
              type="number"
              className="w-full border border-blue-200 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder={`Enter ${field}`}
              value={values[field] ?? ''}
              onChange={(e) => handleChange(field, e.target.value)}
            />
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={handleSubmitAll}
        className="mt-4 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700 transition-colors"
      >
        Submit All
      </button>
    </div>
  )
}

export default FollowUpQuestions
