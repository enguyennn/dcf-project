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

The site deploys automatically to GitHub Pages via GitHub Actions on every push to `main`. No manual deployment steps are required.

**Live URL**: https://t-ethnguyen_microsoft.github.io/DCF-Project/

## Architecture

See the full Product Requirements Document at [`docs/projects/dcf-model-builder/dcf-model-builder.prd.md`](docs/projects/dcf-model-builder/dcf-model-builder.prd.md) for architecture overview, data flow, and implementation details.
