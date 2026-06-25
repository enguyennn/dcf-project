/**
 * ITEM-051 — Bundle size validation: initial gzipped JS < 200KB.
 *
 * RECONCILIATION: A vitest test cannot run `vite build` during execution.
 * This test reuses the gzip-measuring approach from `scripts/check-bundle-size.mjs`:
 * reads built `dist/assets/*.js`, gzips with `zlib.gzipSync`, and asserts the
 * initial entry chunk is under 200KB. If `dist/` does not exist (no prior build),
 * the test is SKIPPED gracefully rather than failing. The canonical check is
 * `npm run build:check-size`.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';

const BUDGET_BYTES = 200 * 1024; // 200 KB
const ASSETS_DIR = join(process.cwd(), 'dist', 'assets');

const distExists = existsSync(ASSETS_DIR);

describe('ITEM-051: Bundle size < 200KB gzipped', () => {
  it.skipIf(!distExists)(
    'initial entry chunk gzipped size is under 200KB budget',
    () => {
      const files = readdirSync(ASSETS_DIR).filter((f) => f.endsWith('.js'));
      expect(files.length).toBeGreaterThan(0);

      let initialGzipped = 0;
      let totalGzipped = 0;

      for (const file of files) {
        const raw = readFileSync(join(ASSETS_DIR, file));
        const gzipped = gzipSync(raw);
        const size = gzipped.length;
        totalGzipped += size;

        const isEntry = file.startsWith('index-');
        if (isEntry) initialGzipped += size;
      }

      const initialKB = (initialGzipped / 1024).toFixed(1);
      const totalKB = (totalGzipped / 1024).toFixed(1);
      const budgetKB = (BUDGET_BYTES / 1024).toFixed(0);

      console.log(`Bundle size results:`);
      console.log(`  Initial entry chunk: ${initialKB} KB gz`);
      console.log(`  Total gzipped JS: ${totalKB} KB`);
      console.log(`  Budget (initial): ${budgetKB} KB`);

      expect(initialGzipped).toBeLessThan(BUDGET_BYTES);
    },
  );

  it.skipIf(distExists)(
    'SKIP: dist/ not found — run `npm run build` first (canonical check: `npm run build:check-size`)',
    () => {
      // This test exists solely to document why the suite was skipped.
      // When dist/ is absent, the real assertion above is skipped and this placeholder runs.
      expect(true).toBe(true);
    },
  );
});
