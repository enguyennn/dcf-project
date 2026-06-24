import { useState, useRef, useCallback } from 'react';
import { parseExcel } from '../utils/parseExcel';
import type { FinancialData } from '../models/financialTypes';

interface FileUploadProps {
  onParsed: (rows: Partial<FinancialData>[]) => void;
}

export default function FileUpload({ onParsed }: FileUploadProps) {
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setLoading(true);
      setErrors([]);
      const result = await parseExcel(file);
      setLoading(false);
      if (result.errors.length > 0) {
        setErrors(result.errors);
      }
      if (result.parsed.length > 0) {
        onParsed(result.parsed);
      }
    },
    [onParsed],
  );

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(true);
  }

  function handleDragLeave() {
    setDragOver(false);
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div className="mb-6">
      <div
        onClick={() => inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          dragOver
            ? 'border-purple-500 bg-purple-50'
            : 'border-gray-300 hover:border-purple-400'
        }`}
      >
        {loading ? (
          <p className="text-gray-600">Parsing file...</p>
        ) : (
          <p className="text-gray-600">
            Drag &amp; drop an Excel file here, or click to browse
          </p>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,.csv"
          className="hidden"
          onChange={handleInputChange}
        />
      </div>
      {errors.length > 0 && (
        <div className="mt-3 space-y-1">
          {errors.map((err, i) => (
            <p key={i} className="text-sm text-red-600">
              {err}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
