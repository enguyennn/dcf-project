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

The site deploys automatically to [Azure Static Web Apps](https://learn.microsoft.com/azure/static-web-apps/) via GitHub Actions on every push to `main`. Pull requests get a temporary preview environment automatically.

**Setup (one-time):** Create an Azure Static Web Apps resource linked to this repo. Azure adds the `AZURE_STATIC_WEB_APPS_API_TOKEN` deployment-token secret to the repo automatically. The build config is `app_location: "/"`, `output_location: "dist"`. Client-side routing falls back to `index.html` via [`public/staticwebapp.config.json`](public/staticwebapp.config.json).

**Live URL**: assigned by Azure when the Static Web App is created (e.g. `https://<name>.azurestaticapps.net`).

## Architecture

See the full Product Requirements Document at [`docs/projects/dcf-model-builder/dcf-model-builder.prd.md`](docs/projects/dcf-model-builder/dcf-model-builder.prd.md) for architecture overview, data flow, and implementation details.
