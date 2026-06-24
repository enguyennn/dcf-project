import type { DCFInputs, ResearchDataSource } from '../models/financialTypes';
import { mergeAssumptions } from '../utils/assumptionEngine';

interface AssumptionsFormProps {
  values: DCFInputs;
  onChange: (field: string, value: number | string) => void;
  researched?: Record<string, ResearchDataSource>;
  onUseManual?: (field: string) => void;
}

interface FieldConfig {
  key: string;
  label: string;
  tooltip: string;
  type: 'number' | 'text' | 'select';
  options?: string[];
}

const COMPANY_FIELDS: FieldConfig[] = [
  { key: 'company.companyName', label: 'Company Name', tooltip: 'Name of the company being valued', type: 'text' },
  { key: 'company.tickerSymbol', label: 'Ticker Symbol', tooltip: 'Stock ticker (optional)', type: 'text' },
  { key: 'company.industry', label: 'Industry', tooltip: 'Industry classification (optional)', type: 'text' },
  { key: 'company.currency', label: 'Currency', tooltip: 'Reporting currency', type: 'select', options: ['USD', 'EUR', 'GBP', 'JPY', 'CAD', 'AUD'] },
];

const OPERATING_FIELDS: FieldConfig[] = [
  { key: 'revenue', label: 'Revenue', tooltip: 'Total annual revenue', type: 'number' },
  { key: 'operatingMarginRate', label: 'Operating Margin Rate', tooltip: 'Operating income as a fraction of revenue', type: 'number' },
  { key: 'dAndARate', label: 'D&A Rate', tooltip: 'Depreciation & amortization as fraction of revenue', type: 'number' },
  { key: 'capExRate', label: 'CapEx Rate', tooltip: 'Capital expenditures as fraction of revenue', type: 'number' },
  { key: 'nwcRate', label: 'NWC Rate', tooltip: 'Change in net working capital as fraction of revenue growth', type: 'number' },
  { key: 'taxRate', label: 'Tax Rate', tooltip: 'Effective corporate tax rate', type: 'number' },
];

const GROWTH_FIELDS: FieldConfig[] = [
  { key: 'revenueGrowthRate', label: 'Revenue Growth Rate', tooltip: 'Expected annual revenue growth rate', type: 'number' },
  { key: 'projectionYears', label: 'Projection Years', tooltip: 'Number of years in explicit forecast period', type: 'number' },
];

const WACC_FIELDS: FieldConfig[] = [
  { key: 'riskFreeRate', label: 'Risk-Free Rate', tooltip: '10-year Treasury yield or equivalent', type: 'number' },
  { key: 'beta', label: 'Beta', tooltip: 'Equity beta (systematic risk measure)', type: 'number' },
  { key: 'equityRiskPremium', label: 'Equity Risk Premium', tooltip: 'Expected excess return of equities over risk-free rate', type: 'number' },
  { key: 'costOfDebt', label: 'Cost of Debt', tooltip: 'Pre-tax borrowing rate', type: 'number' },
  { key: 'debtToEquityRatio', label: 'Debt-to-Equity Ratio', tooltip: 'D/E ratio for capital structure', type: 'number' },
];

const TERMINAL_FIELDS: FieldConfig[] = [
  { key: 'perpetuityGrowthRate', label: 'Perpetuity Growth Rate', tooltip: 'Long-term growth rate for perpetuity method', type: 'number' },
  { key: 'exitMultiple', label: 'Exit Multiple', tooltip: 'EV/EBITDA multiple for exit multiple method', type: 'number' },
];

function getNestedValue(values: DCFInputs, key: string): string | number {
  if (key.startsWith('company.')) {
    const companyKey = key.slice(8) as keyof typeof values.company;
    return values.company[companyKey] ?? '';
  }
  return values[key as keyof DCFInputs] as string | number;
}

function isNumericInvalid(value: number | string, type: string): boolean {
  if (type !== 'number') return false;
  return value === '' || Number.isNaN(Number(value));
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <h3 className="text-lg font-semibold text-gray-800 border-b pb-1">{title}</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {children}
      </div>
    </div>
  );
}

function FormField({ field, value, onChange }: { field: FieldConfig; value: string | number; onChange: (key: string, val: number | string) => void }) {
  const invalid = isNumericInvalid(value, field.type);

  function handleChange(raw: string) {
    if (field.type === 'number') {
      const num = raw === '' ? '' : Number(raw);
      onChange(field.key, num as number | string);
    } else {
      onChange(field.key, raw);
    }
  }

  if (field.type === 'select' && field.options) {
    return (
      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1" title={field.tooltip}>
          {field.label}
        </label>
        <select
          value={String(value)}
          onChange={(e) => onChange(field.key, e.target.value)}
          title={field.tooltip}
          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:ring-2 focus:ring-blue-500"
        >
          {field.options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1" title={field.tooltip}>
        {field.label}
      </label>
      <input
        type={field.type === 'number' ? 'number' : 'text'}
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        title={field.tooltip}
        step={field.type === 'number' ? 'any' : undefined}
        className={`w-full border rounded px-2 py-1.5 text-sm focus:ring-2 focus:ring-blue-500 ${
          invalid ? 'border-red-500' : 'border-gray-300'
        }`}
      />
      {invalid && (
        <p className="text-xs text-red-600 mt-0.5">Required numeric value</p>
      )}
    </div>
  );
}

function AssumptionsForm({ values, onChange, researched, onUseManual }: AssumptionsFormProps) {
  function handleReset() {
    const defaults = mergeAssumptions({});
    const allKeys = Object.keys(defaults) as (keyof DCFInputs)[];
    for (const key of allKeys) {
      if (key === 'company') {
        const companyDefaults = defaults.company;
        onChange('company.companyName', companyDefaults.companyName);
        onChange('company.currency', companyDefaults.currency);
        onChange('company.tickerSymbol', companyDefaults.tickerSymbol ?? '');
        onChange('company.industry', companyDefaults.industry ?? '');
      } else {
        onChange(key, defaults[key] as number | string);
      }
    }
  }

  function renderFields(fields: FieldConfig[]) {
    return fields.map((field) => (
      <FormField
        key={field.key}
        field={field}
        value={getNestedValue(values, field.key)}
        onChange={onChange}
      />
    ));
  }

  return (
    <div className="space-y-6">
      <Section title="Company Info">
        {renderFields(COMPANY_FIELDS)}
      </Section>

      <Section title="Operating Assumptions">
        {renderFields(OPERATING_FIELDS)}
      </Section>

      <Section title="Growth Assumptions">
        {renderFields(GROWTH_FIELDS)}
      </Section>

      <Section title="WACC Components">
        {WACC_FIELDS.map((field) => (
          <div key={field.key}>
            <FormField
              field={field}
              value={getNestedValue(values, field.key)}
              onChange={onChange}
            />
            {researched?.[field.key] && (
              <div className="mt-1 p-1.5 bg-blue-50 border border-blue-100 rounded text-xs text-gray-500">
                <span className="inline-block px-1 py-0.5 bg-blue-100 text-blue-700 rounded text-[10px] font-medium mr-1">Auto-filled</span>
                {researched[field.key].source} &middot;{' '}
                {new Date(researched[field.key].retrievedAt).toLocaleDateString()} &middot;{' '}
                confidence: {researched[field.key].confidence}
                {onUseManual && (
                  <button
                    type="button"
                    onClick={() => onUseManual(field.key)}
                    className="ml-2 text-blue-600 underline hover:text-blue-800"
                  >
                    Use Manual Value Instead
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </Section>

      <Section title="Terminal Value">
        <div className="col-span-full">
          <label className="block text-xs font-medium text-gray-600 mb-1">Method</label>
          <div className="flex gap-4">
            <label className="flex items-center gap-1 text-sm">
              <input
                type="radio"
                name="tvMethod"
                value="perpetuity"
                checked={values.method === 'perpetuity'}
                onChange={() => onChange('method', 'perpetuity')}
              />
              Perpetuity Growth
            </label>
            <label className="flex items-center gap-1 text-sm">
              <input
                type="radio"
                name="tvMethod"
                value="exitMultiple"
                checked={values.method === 'exitMultiple'}
                onChange={() => onChange('method', 'exitMultiple')}
              />
              Exit Multiple
            </label>
          </div>
        </div>
        {renderFields(TERMINAL_FIELDS)}
      </Section>

      <button
        type="button"
        onClick={handleReset}
        className="px-4 py-2 bg-gray-200 text-gray-700 font-medium rounded hover:bg-gray-300 transition-colors"
      >
        Reset to Defaults
      </button>
    </div>
  );
}

export default AssumptionsForm;
