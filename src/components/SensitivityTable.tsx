import { useState } from 'react'
import type { DCFInputs } from '../models/financialTypes'
import { sensitivityMatrix } from '../utils/dcfCalculations'

interface SensitivityTableProps {
  inputs: DCFInputs
}

const SENSITIVITY_FIELDS: { label: string; field: keyof DCFInputs }[] = [
  { label: 'Revenue Growth Rate', field: 'revenueGrowthRate' },
  { label: 'Operating Margin Rate', field: 'operatingMarginRate' },
  { label: 'Perpetuity Growth Rate', field: 'perpetuityGrowthRate' },
  { label: 'Risk-Free Rate', field: 'riskFreeRate' },
  { label: 'Beta', field: 'beta' },
  { label: 'Cost of Debt', field: 'costOfDebt' },
  { label: 'Exit Multiple', field: 'exitMultiple' },
  { label: 'Tax Rate', field: 'taxRate' },
]

/** Per-field step size for building the 5-value range around base */
const STEP_MAP: Partial<Record<keyof DCFInputs, number>> = {
  revenueGrowthRate: 0.005,
  operatingMarginRate: 0.005,
  perpetuityGrowthRate: 0.005,
  riskFreeRate: 0.005,
  costOfDebt: 0.005,
  taxRate: 0.005,
  beta: 0.1,
  exitMultiple: 0.5,
}

function getStep(field: keyof DCFInputs): number {
  return STEP_MAP[field] ?? 0.005
}

function buildRange(base: number, step: number): number[] {
  return [base - 2 * step, base - step, base, base + step, base + 2 * step]
}

function SensitivityTable({ inputs }: SensitivityTableProps) {
  const [xField, setXField] = useState<keyof DCFInputs>('perpetuityGrowthRate')
  const [yField, setYField] = useState<keyof DCFInputs>('riskFreeRate')

  const xBase = inputs[xField] as number
  const yBase = inputs[yField] as number
  const xStep = getStep(xField)
  const yStep = getStep(yField)
  const xValues = buildRange(xBase, xStep)
  const yValues = buildRange(yBase, yStep)

  const matrix = sensitivityMatrix(inputs, xField, xValues, yField, yValues)
  const baseCell = matrix[2][2] // center cell

  const xLabel = SENSITIVITY_FIELDS.find((f) => f.field === xField)?.label ?? xField
  const yLabel = SENSITIVITY_FIELDS.find((f) => f.field === yField)?.label ?? yField

  const isRate = (field: keyof DCFInputs) =>
    field !== 'exitMultiple' && field !== 'beta'

  const fmtAxis = (value: number, field: keyof DCFInputs) =>
    isRate(field) ? (value * 100).toFixed(2) + '%' : value.toFixed(2)

  const fmtPrice = (n: number | null) =>
    n === null ? 'N/A' : n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

  function getCellClass(value: number | null, rowIdx: number, colIdx: number): string {
    if (rowIdx === 2 && colIdx === 2) return 'bg-green-200 font-semibold'
    if (value === null) return 'text-gray-400'
    if (baseCell === null) return ''
    if (value > baseCell) return 'bg-green-50'
    if (value < baseCell) return 'bg-red-50'
    return ''
  }

  return (
    <div className="overflow-x-auto">
      <h3 className="text-lg font-semibold mb-2">Sensitivity Analysis — Implied Share Price</h3>
      {/* Note: riskFreeRate is the default Y-axis as it is the primary WACC driver */}
      <div className="flex gap-4 mb-3">
        <label className="text-sm">
          X-Axis (columns):
          <select
            className="ml-2 border rounded px-2 py-1 text-sm"
            value={xField}
            onChange={(e) => setXField(e.target.value as keyof DCFInputs)}
          >
            {SENSITIVITY_FIELDS.map((f) => (
              <option key={f.field} value={f.field}>{f.label}</option>
            ))}
          </select>
        </label>
        <label className="text-sm">
          Y-Axis (rows):
          <select
            className="ml-2 border rounded px-2 py-1 text-sm"
            value={yField}
            onChange={(e) => setYField(e.target.value as keyof DCFInputs)}
          >
            {SENSITIVITY_FIELDS.map((f) => (
              <option key={f.field} value={f.field}>{f.label}</option>
            ))}
          </select>
        </label>
      </div>
      <p className="text-xs text-gray-500 mb-3">Rows: {yLabel} | Columns: {xLabel}</p>
      <table className="min-w-full text-sm border border-gray-300">
        <thead className="bg-gray-100">
          <tr>
            <th className="px-3 py-2 text-left border-b border-gray-300">{yLabel} \ {xLabel}</th>
            {xValues.map((v, i) => (
              <th key={i} className="px-3 py-2 text-right border-b border-gray-300">{fmtAxis(v, xField)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {yValues.map((yVal, ri) => (
            <tr key={ri} className={ri % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
              <td className="px-3 py-2 font-medium border-b border-gray-200">{fmtAxis(yVal, yField)}</td>
              {xValues.map((_, ci) => (
                <td
                  key={ci}
                  className={`px-3 py-2 text-right border-b border-gray-200 ${getCellClass(matrix[ri][ci], ri, ci)}`}
                >
                  {fmtPrice(matrix[ri][ci])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default SensitivityTable
