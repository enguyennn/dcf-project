import type { DCFInputs } from '../models/financialTypes'
import { calculateWACC, sensitivityAnalysis } from '../utils/dcfCalculations'

interface SensitivityTableProps {
  inputs: DCFInputs
}

function SensitivityTable({ inputs }: SensitivityTableProps) {
  const baseWACC = calculateWACC(
    inputs.riskFreeRate,
    inputs.beta,
    inputs.equityRiskPremium,
    inputs.costOfDebt,
    inputs.debtToEquityRatio,
    inputs.taxRate,
  )
  const baseGrowth = inputs.perpetuityGrowthRate

  const waccRange = [
    baseWACC - 0.01,
    baseWACC - 0.005,
    baseWACC,
    baseWACC + 0.005,
    baseWACC + 0.01,
  ]
  const growthRange = [
    baseGrowth - 0.01,
    baseGrowth - 0.005,
    baseGrowth,
    baseGrowth + 0.005,
    baseGrowth + 0.01,
  ]

  const matrix = sensitivityAnalysis(inputs, waccRange, growthRange)
  const baseCell = matrix[2][2]

  const fmtPct = (n: number) => (n * 100).toFixed(2) + '%'
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
      <p className="text-xs text-gray-500 mb-3">Rows: WACC | Columns: Perpetuity Growth Rate</p>
      <table className="min-w-full text-sm border border-gray-300">
        <thead className="bg-gray-100">
          <tr>
            <th className="px-3 py-2 text-left border-b border-gray-300">WACC \ Growth</th>
            {growthRange.map((g, i) => (
              <th key={i} className="px-3 py-2 text-right border-b border-gray-300">{fmtPct(g)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {waccRange.map((w, ri) => (
            <tr key={ri} className={ri % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
              <td className="px-3 py-2 font-medium border-b border-gray-200">{fmtPct(w)}</td>
              {growthRange.map((_, ci) => (
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
