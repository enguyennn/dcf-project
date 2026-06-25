// Real-network p95 validation for ITEM-050 (success metric: p95 ≤ 8s).
//
// The vitest suite (tests/e2e/performance.test.ts) only measures STRUCTURAL
// pipeline latency with a mocked `parseWithAI`, because there is no network in
// the node test environment. This script closes that gap by measuring the REAL
// round-trip latency of the deployed `/api/parse` endpoint (LLM call included).
//
// Usage (PowerShell):
//   $env:PARSE_ENDPOINT = "https://<your-deployment>.vercel.app/api/parse"
//   node scripts/validate-p95.mjs
// or:
//   node scripts/validate-p95.mjs https://<your-deployment>.vercel.app/api/parse
//
// Requires Node 18+ (global fetch). Exits non-zero if p95 exceeds the budget.

const P95_BUDGET_MS = 8_000;
const NUM_RUNS = 25; // > 20, matches the success-metric sample size

const ENDPOINT = process.argv[2] || process.env.PARSE_ENDPOINT;

if (!ENDPOINT) {
  console.error(
    'ERROR: No endpoint provided. Pass the deployed /api/parse URL as an argument\n' +
      '       or set the PARSE_ENDPOINT environment variable.',
  );
  process.exit(2);
}

const INPUTS = [
  'A mid-size SaaS company growing 30% YoY with 70% gross margins',
  'An e-commerce retailer doing $200M in annual sales',
  'A biotech startup with $50M in funding and no revenue',
  'A fintech processor handling $10B volume',
  'Enterprise cloud provider with $1B ARR',
];

function percentile(sorted, p) {
  const index = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, index)];
}

async function main() {
  console.log(`Validating real-network p95 against: ${ENDPOINT}`);
  console.log(`Runs: ${NUM_RUNS}  Budget: ${P95_BUDGET_MS}ms\n`);

  const timings = [];
  let failures = 0;

  for (let i = 0; i < NUM_RUNS; i++) {
    const description = INPUTS[i % INPUTS.length];
    const start = performance.now();
    try {
      const res = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: description }),
      });
      const elapsed = performance.now() - start;
      if (!res.ok) {
        failures++;
        console.warn(`  run ${i + 1}: HTTP ${res.status} (${elapsed.toFixed(0)}ms)`);
      } else {
        // Drain the body so the connection completes before timing is trusted.
        await res.json().catch(() => undefined);
        timings.push(elapsed);
      }
    } catch (err) {
      failures++;
      console.warn(`  run ${i + 1}: request failed — ${err.message}`);
    }
  }

  if (timings.length === 0) {
    console.error('\nAll requests failed. Cannot compute p95.');
    process.exit(1);
  }

  timings.sort((a, b) => a - b);
  const p95 = percentile(timings, 95);

  console.log('\nResults:');
  console.log(`  successful runs: ${timings.length}/${NUM_RUNS}  (failures: ${failures})`);
  console.log(`  min:    ${timings[0].toFixed(0)}ms`);
  console.log(`  median: ${percentile(timings, 50).toFixed(0)}ms`);
  console.log(`  p95:    ${p95.toFixed(0)}ms`);
  console.log(`  max:    ${timings[timings.length - 1].toFixed(0)}ms`);
  console.log(`  budget: ${P95_BUDGET_MS}ms`);

  if (p95 > P95_BUDGET_MS) {
    console.error(`\n❌ p95 ${p95.toFixed(0)}ms exceeds budget ${P95_BUDGET_MS}ms`);
    process.exit(1);
  }
  console.log(`\n✅ p95 under budget (${(P95_BUDGET_MS - p95).toFixed(0)}ms headroom)`);
}

main();
