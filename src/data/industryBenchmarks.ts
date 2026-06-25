import type { IndustryBenchmark } from '../models/aiTypes';

/** Curated industry benchmark dataset. All rate fields are decimals in [0,1]. */
export const INDUSTRY_BENCHMARKS: IndustryBenchmark[] = [
  {
    industry: 'SaaS',
    aliases: ['saas', 'software', 'cloud software', 'b2b software', 'software as a service'],
    revenueGrowthRate: 0.25,
    operatingMarginRate: 0.20,
    dAndARate: 0.05,
    capExRate: 0.03,
    nwcRate: 0.08,
    costOfDebt: 0.05,
    betaRange: { low: 1.0, mid: 1.3, high: 1.6 },
  },
  {
    industry: 'Manufacturing',
    aliases: ['manufacturing', 'industrial', 'industrials', 'factory'],
    revenueGrowthRate: 0.05,
    operatingMarginRate: 0.12,
    dAndARate: 0.06,
    capExRate: 0.07,
    nwcRate: 0.15,
    costOfDebt: 0.045,
    betaRange: { low: 0.8, mid: 1.0, high: 1.3 },
  },
  {
    industry: 'Retail',
    aliases: ['retail', 'e-commerce', 'ecommerce', 'consumer retail'],
    revenueGrowthRate: 0.08,
    operatingMarginRate: 0.06,
    dAndARate: 0.04,
    capExRate: 0.05,
    nwcRate: 0.12,
    costOfDebt: 0.05,
    betaRange: { low: 0.8, mid: 1.0, high: 1.2 },
  },
  {
    industry: 'Healthcare',
    aliases: ['healthcare', 'health', 'biotech', 'pharma', 'pharmaceuticals'],
    revenueGrowthRate: 0.10,
    operatingMarginRate: 0.15,
    dAndARate: 0.04,
    capExRate: 0.05,
    nwcRate: 0.10,
    costOfDebt: 0.04,
    betaRange: { low: 0.7, mid: 0.9, high: 1.2 },
  },
  {
    industry: 'Fintech',
    aliases: ['fintech', 'financial technology', 'payments', 'digital payments'],
    revenueGrowthRate: 0.20,
    operatingMarginRate: 0.18,
    dAndARate: 0.04,
    capExRate: 0.04,
    nwcRate: 0.06,
    costOfDebt: 0.05,
    betaRange: { low: 1.0, mid: 1.3, high: 1.5 },
  },
  {
    industry: 'Energy',
    aliases: ['energy', 'oil and gas', 'oil & gas', 'utilities', 'renewable energy'],
    revenueGrowthRate: 0.04,
    operatingMarginRate: 0.14,
    dAndARate: 0.08,
    capExRate: 0.12,
    nwcRate: 0.10,
    costOfDebt: 0.045,
    betaRange: { low: 0.7, mid: 1.0, high: 1.3 },
  },
  {
    industry: 'Consumer Goods',
    aliases: ['consumer goods', 'cpg', 'fmcg', 'consumer products', 'packaged goods'],
    revenueGrowthRate: 0.06,
    operatingMarginRate: 0.14,
    dAndARate: 0.04,
    capExRate: 0.05,
    nwcRate: 0.12,
    costOfDebt: 0.04,
    betaRange: { low: 0.6, mid: 0.8, high: 1.0 },
  },
  {
    industry: 'Real Estate',
    aliases: ['real estate', 'reit', 'property', 'commercial real estate'],
    revenueGrowthRate: 0.05,
    operatingMarginRate: 0.30,
    dAndARate: 0.07,
    capExRate: 0.10,
    nwcRate: 0.05,
    costOfDebt: 0.04,
    betaRange: { low: 0.6, mid: 0.8, high: 1.1 },
  },
  {
    industry: 'Telecom',
    aliases: ['telecom', 'telecommunications', 'telco', 'wireless'],
    revenueGrowthRate: 0.03,
    operatingMarginRate: 0.20,
    dAndARate: 0.10,
    capExRate: 0.15,
    nwcRate: 0.05,
    costOfDebt: 0.045,
    betaRange: { low: 0.6, mid: 0.7, high: 0.9 },
  },
  {
    industry: 'Media',
    aliases: ['media', 'entertainment', 'streaming', 'digital media', 'content'],
    revenueGrowthRate: 0.12,
    operatingMarginRate: 0.16,
    dAndARate: 0.06,
    capExRate: 0.04,
    nwcRate: 0.08,
    costOfDebt: 0.05,
    betaRange: { low: 0.9, mid: 1.1, high: 1.4 },
  },
];

/**
 * Fuzzy-match an industry string against the benchmark dataset.
 * Case-insensitive; matches on exact industry name, aliases, or substring containment.
 * Returns the first match or undefined.
 */
export function lookupBenchmark(industry: string): IndustryBenchmark | undefined {
  const trimmed = industry.trim().toLowerCase();
  if (trimmed === '') return undefined;

  for (const benchmark of INDUSTRY_BENCHMARKS) {
    const name = benchmark.industry.toLowerCase();
    // Exact match on industry name
    if (trimmed === name) return benchmark;
    // Substring: input contained in industry name or vice versa
    if (name.includes(trimmed) || trimmed.includes(name)) return benchmark;
    // Alias match: exact or substring containment
    for (const alias of benchmark.aliases) {
      if (trimmed === alias) return benchmark;
      if (alias.includes(trimmed) || trimmed.includes(alias)) return benchmark;
    }
  }

  return undefined;
}
