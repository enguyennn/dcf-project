import type { AssumptionSource } from '../models/financialTypes';
import { sourceBadgeStyle } from './sourceMetadata';

interface SourceBadgeProps {
  source: AssumptionSource;
  rationale?: string;
}

export default function SourceBadge({ source, rationale }: SourceBadgeProps) {
  const { label, className } = sourceBadgeStyle(source);
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${className}`}
      title={rationale}
    >
      {label}
    </span>
  );
}
