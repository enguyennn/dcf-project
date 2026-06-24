import { useState } from 'react'
import type { DCFInputs, DCFOutputs } from '../models/financialTypes'

interface ComparablesProps {
  inputs: DCFInputs
  outputs: DCFOutputs
}

function Comparables({ inputs, outputs }: ComparablesProps) {
  const [peerEVEBITDA, setPeerEVEBITDA] = useState<number>(10)
  const [peerPE, setPeerPE] = useState<number>(15)

  // Implied EV/EBITDA = enterpriseValue / baseEBITDA
  // baseEBITDA = operatingIncome + depreciationAmortization
  const baseEBITDA = inputs.operatingIncome + inputs.depreciationAmortization
  const impliedEVEBITDA = baseEBITDA !== 0 ? outputs.enterpriseValue / baseEBITDA : null

  // Implied P/E = impliedSharePrice / EPS
  // EPS = NOPAT proxy / sharesOutstanding = (operatingIncome * (1 - taxRate)) / sharesOutstanding
  const nopat = inputs.operatingIncome * (1 - inputs.taxRate)
  const eps = inputs.sharesOutstanding > 0 ? nopat / inputs.sharesOutstanding : null
  const impliedPE = eps && eps !== 0 ? outputs.impliedSharePrice / eps : null

  const fmtMultiple = (n: number | null) =>
    n === null ? 'N/A' : n.toFixed(2) + 'x'

  function comparison(implied: number | null, peer: number): string {
    if (implied === null) return ''
    if (implied > peer) return '↑ Higher than peers'
    if (implied < peer) return '↓ Lower than peers'
    return '= In line with peers'
  }

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold">Comparable Multiples Analysis</h3>
      <p className="text-xs text-gray-500">
        Implied multiples are derived from DCF outputs. EV/EBITDA uses operatingIncome + D&A as EBITDA proxy.
        P/E uses NOPAT (operatingIncome × (1−taxRate)) / sharesOutstanding as EPS proxy.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Peer inputs */}
        <div className="space-y-4">
          <h4 className="font-medium text-sm">Peer Averages</h4>
          <label className="block text-sm">
            Peer Average EV/EBITDA:
            <input
              type="number"
              step="0.5"
              value={peerEVEBITDA}
              onChange={(e) => setPeerEVEBITDA(parseFloat(e.target.value) || 0)}
              className="ml-2 w-24 border rounded px-2 py-1 text-sm"
            />
          </label>
          <label className="block text-sm">
            Peer Average P/E:
            <input
              type="number"
              step="0.5"
              value={peerPE}
              onChange={(e) => setPeerPE(parseFloat(e.target.value) || 0)}
              className="ml-2 w-24 border rounded px-2 py-1 text-sm"
            />
          </label>
        </div>

        {/* Comparison table */}
        <div>
          <table className="text-sm border border-gray-300 w-full">
            <thead className="bg-gray-100">
              <tr>
                <th className="px-3 py-2 text-left border-b border-gray-300">Metric</th>
                <th className="px-3 py-2 text-right border-b border-gray-300">DCF Implied</th>
                <th className="px-3 py-2 text-right border-b border-gray-300">Peer Avg</th>
                <th className="px-3 py-2 text-left border-b border-gray-300">Note</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="px-3 py-2 border-b border-gray-200">EV/EBITDA</td>
                <td className="px-3 py-2 text-right border-b border-gray-200">{fmtMultiple(impliedEVEBITDA)}</td>
                <td className="px-3 py-2 text-right border-b border-gray-200">{fmtMultiple(peerEVEBITDA)}</td>
                <td className="px-3 py-2 border-b border-gray-200 text-xs text-gray-600">{comparison(impliedEVEBITDA, peerEVEBITDA)}</td>
              </tr>
              <tr>
                <td className="px-3 py-2 border-b border-gray-200">P/E</td>
                <td className="px-3 py-2 text-right border-b border-gray-200">{fmtMultiple(impliedPE)}</td>
                <td className="px-3 py-2 text-right border-b border-gray-200">{fmtMultiple(peerPE)}</td>
                <td className="px-3 py-2 border-b border-gray-200 text-xs text-gray-600">{comparison(impliedPE, peerPE)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

export default Comparables
