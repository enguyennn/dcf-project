import type { DCFInputs, DCFOutputs } from '../models/financialTypes'
import { projectMargins } from '../utils/dcfCalculations'

interface DcfOutputTableProps {
  outputs: DCFOutputs
  inputs: DCFInputs
}

function DcfOutputTable({ outputs, inputs }: DcfOutputTableProps) {
  const margins = projectMargins(
    inputs.revenue,
    outputs.projectedRevenue,
    inputs.operatingMarginRate,
    inputs.dAndARate,
    inputs.capExRate,
    inputs.nwcRate,
    inputs.taxRate,
  )

  const years = outputs.projectedRevenue.length

  const fmt = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 0 })
  const fmtPct = (n: number) => (n * 100).toFixed(2) + '%'
  const fmtPrice = (n: number) => n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

  const tvPctOfEV = outputs.enterpriseValue !== 0
    ? (outputs.terminalValue / outputs.enterpriseValue) * 100
    : 0

  return (
    <div className="space-y-6">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm border border-gray-300">
          <thead className="bg-gray-100">
            <tr>
              <th className="px-3 py-2 text-left border-b border-gray-300">Year</th>
              <th className="px-3 py-2 text-right border-b border-gray-300">Revenue</th>
              <th className="px-3 py-2 text-right border-b border-gray-300">Operating Income</th>
              <th className="px-3 py-2 text-right border-b border-gray-300">NOPAT</th>
              <th className="px-3 py-2 text-right border-b border-gray-300">D&A</th>
              <th className="px-3 py-2 text-right border-b border-gray-300">CapEx</th>
              <th className="px-3 py-2 text-right border-b border-gray-300">ΔNWC</th>
              <th className="px-3 py-2 text-right border-b border-gray-300">FCFF</th>
              <th className="px-3 py-2 text-right border-b border-gray-300">Discount Factor</th>
              <th className="px-3 py-2 text-right border-b border-gray-300">PV of FCFF</th>
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: years }, (_, i) => (
              <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                <td className="px-3 py-2 border-b border-gray-200">{i + 1}</td>
                <td className="px-3 py-2 text-right border-b border-gray-200">{fmt(outputs.projectedRevenue[i])}</td>
                <td className="px-3 py-2 text-right border-b border-gray-200">{fmt(margins.operatingIncome[i])}</td>
                <td className="px-3 py-2 text-right border-b border-gray-200">{fmt(margins.nopat[i])}</td>
                <td className="px-3 py-2 text-right border-b border-gray-200">{fmt(margins.dAndA[i])}</td>
                <td className="px-3 py-2 text-right border-b border-gray-200">{fmt(margins.capEx[i])}</td>
                <td className="px-3 py-2 text-right border-b border-gray-200">{fmt(margins.deltaNWC[i])}</td>
                <td className="px-3 py-2 text-right border-b border-gray-200">{fmt(outputs.projectedFCFF[i])}</td>
                <td className="px-3 py-2 text-right border-b border-gray-200">{fmtPct(outputs.discountFactors[i])}</td>
                <td className="px-3 py-2 text-right border-b border-gray-200">{fmt(outputs.pvFCFF[i])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div className="p-3 bg-gray-50 rounded border border-gray-200">
          <div className="text-gray-500">Terminal Value</div>
          <div className="font-semibold">{fmt(outputs.terminalValue)}</div>
        </div>
        <div className="p-3 bg-gray-50 rounded border border-gray-200">
          <div className="text-gray-500">PV of Terminal Value</div>
          <div className="font-semibold">{fmt(outputs.pvTerminalValue)}</div>
        </div>
        <div className="p-3 bg-gray-50 rounded border border-gray-200">
          <div className="text-gray-500">Enterprise Value</div>
          <div className="font-semibold">{fmt(outputs.enterpriseValue)}</div>
        </div>
        <div className="p-3 bg-gray-50 rounded border border-gray-200">
          <div className="text-gray-500">TV as % of EV</div>
          <div className="font-semibold">{tvPctOfEV.toFixed(2)}%</div>
        </div>
        <div className="p-3 bg-gray-50 rounded border border-gray-200">
          <div className="text-gray-500">Net Debt</div>
          <div className="font-semibold">{fmt(inputs.netDebt)}</div>
        </div>
        <div className="p-3 bg-gray-50 rounded border border-gray-200">
          <div className="text-gray-500">Equity Value</div>
          <div className="font-semibold">{fmt(outputs.equityValue)}</div>
        </div>
        <div className="p-3 bg-gray-50 rounded border border-gray-200">
          <div className="text-gray-500">Diluted Shares</div>
          <div className="font-semibold">{fmt(inputs.sharesOutstanding)}</div>
        </div>
        <div className="p-3 bg-gray-50 rounded border border-gray-200">
          <div className="text-gray-500">Implied Share Price</div>
          <div className="font-semibold">${fmtPrice(outputs.impliedSharePrice)}</div>
        </div>
      </div>
    </div>
  )
}

export default DcfOutputTable
