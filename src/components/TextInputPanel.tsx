import { useState } from 'react';
import { parsePlainText } from '../utils/parsePlainText';
import type { FinancialData } from '../models/financialTypes';

interface TextInputPanelProps {
  onParsed: (parsed: Partial<FinancialData>) => void;
}

function TextInputPanel({ onParsed }: TextInputPanelProps) {
  const [text, setText] = useState('');
  const [errors, setErrors] = useState<string[]>([]);

  function handleParse() {
    const result = parsePlainText(text);
    setErrors(result.errors);
    if (Object.keys(result.parsed).length > 0) {
      onParsed(result.parsed);
    }
  }

  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium text-gray-700">
        Paste Financial Data
      </label>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Revenue: 1,000,000&#10;Operating Income: 150,000&#10;CapEx: 50K"
        className="w-full min-h-40 font-mono border border-gray-300 rounded p-3 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
      />
      <button
        type="button"
        onClick={handleParse}
        className="px-4 py-2 bg-green-600 text-white font-medium rounded hover:bg-green-700 transition-colors"
      >
        Parse
      </button>
      {errors.length > 0 && (
        <div className="space-y-1">
          <p className="text-sm font-medium text-red-600">Unrecognized lines:</p>
          <ul className="list-disc list-inside text-sm text-red-600">
            {errors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default TextInputPanel;
