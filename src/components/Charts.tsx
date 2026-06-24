import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import type { DCFInputs, DCFOutputs } from '../models/financialTypes'
import { sensitivityMatrix } from '../utils/dcfCalculations'

interface ChartsProps {
  inputs: DCFInputs
  outputs: DCFOutputs
}

function Charts({ inputs, outputs }: ChartsProps) {
  // Chart 1: EV Buildup — cumulative stacked bar of PV FCFF + PV Terminal Value
  const evData = outputs.pvFCFF.map((pv, i) => ({
    name: `Year ${i + 1}`,
    pvFCFF: Math.round(pv),
  }))
  evData.push({ name: 'Terminal', pvFCFF: Math.round(outputs.pvTerminalValue) })

  // Chart 2: Sensitivity heatmap as colored HTML table (simple approach — more
  // accessible and lighter than Recharts scatter)
  const heatXValues = [
    inputs.perpetuityGrowthRate - 0.01,
    inputs.perpetuityGrowthRate - 0.005,
    inputs.perpetuityGrowthRate,
    inputs.perpetuityGrowthRate + 0.005,
    inputs.perpetuityGrowthRate + 0.01,
  ]
  const heatYValues = [
    inputs.riskFreeRate - 0.01,
    inputs.riskFreeRate - 0.005,
    inputs.riskFreeRate,
    inputs.riskFreeRate + 0.005,
    inputs.riskFreeRate + 0.01,
  ]
  const heatMatrix = sensitivityMatrix(inputs, 'perpetuityGrowthRate', heatXValues, 'riskFreeRate', heatYValues)
  const heatBase = heatMatrix[2][2]

  function heatColor(val: number | null, ri: number, ci: number): string {
    if (ri === 2 && ci === 2) return '#bbf7d0'
    if (val === null) return '#f3f4f6'
    if (heatBase === null) return '#ffffff'
    if (val > heatBase) return '#dcfce7'
    if (val < heatBase) return '#fee2e2'
    return '#ffffff'
  }

  // Chart 3: Line chart of Revenue & FCFF
  const lineData = outputs.projectedRevenue.map((rev, i) => ({
    year: i + 1,
    Revenue: Math.round(rev),
    FCFF: Math.round(outputs.projectedFCFF[i]),
  }))

  const fmtPct = (n: number) => (n * 100).toFixed(2) + '%'
  const fmtPrice = (n: number | null) =>
    n === null ? 'N/A' : n.toLocaleString(undefined, { maximumFractionDigits: 0 })

  return (
    <div className="space-y-8">
      {/* Chart 1: EV Buildup */}
      <div role="img" aria-label="Enterprise Value buildup bar chart showing PV of FCFF per year plus terminal value">
        <h3 className="text-lg font-semibold mb-2">Enterprise Value Buildup</h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={evData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="pvFCFF" fill="#3b82f6" name="PV Component" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Chart 2: Sensitivity Heatmap (colored HTML table) */}
      <div role="img" aria-label="Sensitivity heatmap showing implied share price across perpetuity growth rate and risk-free rate">
        <h3 className="text-lg font-semibold mb-2">Sensitivity Heatmap</h3>
        <p className="text-xs text-gray-500 mb-2">Rows: Risk-Free Rate | Columns: Perpetuity Growth Rate</p>
        <div className="overflow-x-auto">
          <table className="text-xs border border-gray-300">
            <thead>
              <tr>
                <th className="px-2 py-1 border border-gray-300">RFR \ Growth</th>
                {heatXValues.map((v, i) => (
                  <th key={i} className="px-2 py-1 border border-gray-300">{fmtPct(v)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {heatYValues.map((yVal, ri) => (
                <tr key={ri}>
                  <td className="px-2 py-1 border border-gray-300 font-medium">{fmtPct(yVal)}</td>
                  {heatXValues.map((_, ci) => (
                    <td
                      key={ci}
                      className="px-2 py-1 border border-gray-300 text-right"
                      style={{ backgroundColor: heatColor(heatMatrix[ri][ci], ri, ci) }}
                    >
                      {fmtPrice(heatMatrix[ri][ci])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Chart 3: Revenue & FCFF Line Chart */}
      <div role="img" aria-label="Line chart of projected revenue and free cash flow over projection years">
        <h3 className="text-lg font-semibold mb-2">Revenue & FCFF Projections</h3>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={lineData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="year" label={{ value: 'Year', position: 'insideBottom', offset: -5 }} />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="Revenue" stroke="#3b82f6" />
            <Line type="monotone" dataKey="FCFF" stroke="#10b981" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export default Charts
