# DCF Model Builder

An educational, browser-based Discounted Cash Flow (DCF) valuation web application. This tool allows users to input financial assumptions and receive a transparent FCFF-based enterprise valuation with sensitivity analysis. **This is not investment advice.**

## Tech Stack

- React 18
- TypeScript 5
- Vite 6
- Tailwind CSS v3
- Vitest

## Setup

```bash
npm install
npm run dev
```

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start development server |
| `npm run build` | Type-check and build for production |
| `npm test` | Run unit tests (watch mode) |
| `npm run test:coverage` | Run tests with coverage report |
| `npm run lint` | Lint with ESLint |
| `npm run preview` | Preview production build locally |

## Deployment

The site deploys automatically to [Vercel](https://vercel.com/) via Vercel's native Git integration on every push to `main`. Pull requests get a preview deployment automatically.

**Setup (one-time):** Import this repo at [vercel.com/new](https://vercel.com/new). Vercel auto-detects the Vite framework preset (build command `npm run build`, output directory `dist`). Client-side routing falls back to `index.html` via [`vercel.json`](vercel.json). No GitHub Actions workflow or secrets are required.

**Live URL**: assigned by Vercel when the project is created (e.g. `https://<project>.vercel.app`).

## Architecture

See the full Product Requirements Document at [`docs/projects/dcf-model-builder/dcf-model-builder.prd.md`](docs/projects/dcf-model-builder/dcf-model-builder.prd.md) for architecture overview, data flow, and implementation details.
