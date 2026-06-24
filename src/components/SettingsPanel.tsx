import { useState } from 'react';
import { fetchMarketData } from '../utils/researchApi';
import type { ResearchDataSource } from '../models/financialTypes';

type ResearchField = 'riskFreeRate' | 'beta' | 'equityRiskPremium';

interface SettingsPanelProps {
  onResearched: (data: Partial<Record<ResearchField, ResearchDataSource>>) => void;
}

function SettingsPanel({ onResearched }: SettingsPanelProps) {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('dcf.apiKey') ?? '');
  const [ticker, setTicker] = useState('');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  function handleKeyChange(value: string) {
    setApiKey(value);
    localStorage.setItem('dcf.apiKey', value);
  }

  async function handleFetch() {
    setLoading(true);
    setErrors([]);
    const result = await fetchMarketData(ticker, apiKey);
    onResearched(result.data);
    setErrors(result.errors);
    setLoading(false);
  }

  return (
    <div className="mb-4 p-4 border border-gray-200 rounded bg-gray-50 space-y-3">
      <h3 className="text-sm font-semibold text-gray-700">Market Data Research</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => handleKeyChange(e.target.value)}
            placeholder="Alpha Vantage API key"
            className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Ticker</label>
          <input
            type="text"
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            placeholder="e.g. AAPL"
            className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
          />
        </div>
      </div>
      <button
        type="button"
        onClick={handleFetch}
        disabled={loading}
        className="px-4 py-1.5 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700 disabled:opacity-50 transition-colors"
      >
        {loading ? 'Fetching…' : 'Fetch Market Data'}
      </button>
      <p className="text-xs text-gray-400">
        Your API key is stored only in your browser (localStorage) and never sent anywhere except the data provider.
      </p>
      {errors.length > 0 && (
        <div className="space-y-1">
          {errors.map((err, i) => (
            <p key={i} className="text-xs text-red-600">{err}</p>
          ))}
        </div>
      )}
    </div>
  );
}

export default SettingsPanel;
