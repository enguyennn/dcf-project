/**
 * check-bundle-size.mjs — Pre-push build size gate.
 *
 * Gzips each JS file in dist/assets/, prints sizes, then checks that
 * the initial entry chunk (index-*.js) is under the 200KB gzipped budget
 * per CON-001. Lazy-loaded split chunks (recharts, xlsx, etc.) are printed
 * for visibility but not counted against the budget.
 *
 * Usage: npm run build:check-size
 *   (which runs: npm run build && node scripts/check-bundle-size.mjs)
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';

const BUDGET_BYTES = 200 * 1024; // 200 KB
const ASSETS_DIR = join('dist', 'assets');

let initialGzipped = 0;
let totalGzipped = 0;

const files = readdirSync(ASSETS_DIR).filter((f) => f.endsWith('.js'));

for (const file of files) {
  const raw = readFileSync(join(ASSETS_DIR, file));
  const gzipped = gzipSync(raw);
  const size = gzipped.length;
  totalGzipped += size;
  const isEntry = file.startsWith('index-');
  if (isEntry) initialGzipped += size;
  console.log(`  ${file}: ${(size / 1024).toFixed(1)} KB gz${isEntry ? ' [entry]' : ' [lazy]'}`);
}

const initialKB = (initialGzipped / 1024).toFixed(1);
const totalKB = (totalGzipped / 1024).toFixed(1);
const budgetKB = (BUDGET_BYTES / 1024).toFixed(0);

console.log(`\nInitial entry chunk: ${initialKB} KB gz`);
console.log(`Total gzipped JS: ${totalKB} KB (including lazy splits)`);
console.log(`Budget (initial): ${budgetKB} KB`);

if (initialGzipped > BUDGET_BYTES) {
  console.error(`\n❌ OVER BUDGET by ${((initialGzipped - BUDGET_BYTES) / 1024).toFixed(1)} KB`);
  process.exit(1);
} else {
  console.log(`✅ Under budget (${((BUDGET_BYTES - initialGzipped) / 1024).toFixed(1)} KB remaining)`);
}
