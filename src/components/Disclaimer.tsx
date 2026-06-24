import { useState } from 'react'

interface DisclaimerProps {
  minimizable?: boolean
}

function Disclaimer({ minimizable = false }: DisclaimerProps) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="border-2 border-yellow-500 bg-yellow-50 p-4 rounded">
      <div className="flex items-start justify-between gap-2">
        <div>
          <span className="mr-2">⚠️</span>
          {collapsed ? (
            <span className="text-sm text-yellow-800">Disclaimer (click to expand)</span>
          ) : (
            <span className="text-sm text-yellow-800">
              For educational and analytical purposes only. Not investment advice. Results are entirely dependent on user-provided assumptions and may not reflect actual company value.
            </span>
          )}
        </div>
        {minimizable && (
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            className="text-yellow-700 hover:text-yellow-900 text-sm font-medium shrink-0"
            aria-expanded={!collapsed}
            aria-label={collapsed ? 'Expand disclaimer' : 'Collapse disclaimer'}
          >
            {collapsed ? 'Show' : 'Hide'}
          </button>
        )}
      </div>
    </div>
  )
}

export default Disclaimer
