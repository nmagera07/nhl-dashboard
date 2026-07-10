# Frontend — NHL Stats Dashboard

React + Vite single-page app. All UI, including component-scoped styles,
lives in [`src/App.jsx`](src/App.jsx) — see the [top-level README](../README.md)
for what the app actually does.

## Setup

```
npm install
npm run dev
```

By default this points at the live deployed backend (`API_BASE` at the
top of `App.jsx`). To run against a local backend instead, change
`API_BASE` to `http://127.0.0.1:8000` and run `uvicorn api:app --reload`
from `../backend` (see [`../backend/README.md`](../backend/README.md)).

## Build

```
npm run build
```

## Lint

```
npm run lint
```

## Deployment

Deployed to Azure Static Web Apps via GitHub Actions
(`.github/workflows/azure-static-web-apps-*.yml`) on every push to `main`.
