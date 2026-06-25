import type { AssumptionMetadata } from '../models/aiTypes';
import { summarizeSources } from './sourceMetadata';

interface AssumptionSummaryProps {
  metadata: AssumptionMetadata[];
}

export default function AssumptionSummary({ metadata }: AssumptionSummaryProps) {
  const summary = summarizeSources(metadata);
  if (summary.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-gray-600">
      {summary.map((s, i) => (
        <span key={s.source}>
          <span className="font-medium">{s.count}</span> {s.label}
          {i < summary.length - 1 && <span className="ml-2">·</span>}
        </span>
      ))}
    </div>
  );
}
