import type { AssumptionSource } from '../models/financialTypes';
import type { AssumptionMetadata } from '../models/aiTypes';

/** Returns the display label and Tailwind color class for a given AssumptionSource. */
export function sourceBadgeStyle(source: AssumptionSource): { label: string; className: string } {
  switch (source) {
    case 'market-data':
      return { label: 'Market Data', className: 'bg-blue-100 text-blue-800' };
    case 'ai-inferred':
      return { label: 'AI Inferred', className: 'bg-purple-100 text-purple-800' };
    case 'industry-benchmark':
      return { label: 'Industry Benchmark', className: 'bg-green-100 text-green-800' };
    case 'default':
      return { label: 'Default', className: 'bg-gray-100 text-gray-800' };
    case 'user-provided':
      return { label: 'User Provided', className: 'bg-orange-100 text-orange-800' };
  }
}

/** Counts metadata entries by source, returns a stable-ordered array omitting zero-count sources. */
export function summarizeSources(
  metadata: AssumptionMetadata[],
): { source: AssumptionSource; count: number; label: string }[] {
  const order: AssumptionSource[] = [
    'ai-inferred',
    'market-data',
    'industry-benchmark',
    'default',
    'user-provided',
  ];
  const counts = new Map<AssumptionSource, number>();
  for (const m of metadata) {
    counts.set(m.source, (counts.get(m.source) ?? 0) + 1);
  }
  return order
    .filter((s) => (counts.get(s) ?? 0) > 0)
    .map((s) => ({
      source: s,
      count: counts.get(s)!,
      label: sourceBadgeStyle(s).label,
    }));
}
