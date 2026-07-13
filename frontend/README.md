# Frontend — NHL Stats Dashboard

React + Vite single-page app, split into `src/pages/` (one per route),
`src/components/` (reusable UI), and `src/hooks/` — see the
[top-level README](../README.md) for what the app actually does.

## Setup

```
npm install
npm run dev
```

By default this points at the live deployed backend (`API_BASE` in
[`src/config.js`](src/config.js)). To run against a local backend
instead, change `API_BASE` to `http://127.0.0.1:8000` and run
`uvicorn api:app --reload` from `../backend` (see
[`../backend/README.md`](../backend/README.md)).

## Build

```
npm run build
```

## Lint

```
npm run lint
```

## Tests

```
npm test          # run once
npm run test:watch  # re-run on file changes
```

Vitest + React Testing Library, `jsdom` environment. Tests live next to
the file they cover (`Foo.jsx` → `Foo.test.jsx`), not in a separate
mirrored directory. `global.fetch`/`globalThis.fetch` is stubbed with
`vi.fn()` per test rather than hitting a real network call, mirroring
the backend suite's "mock the one seam that does I/O" approach.

Current coverage (33 tests): `useFetchWithStatus` (the shared fetch/
loading/error hook), `LeaderboardPanel` (sort/filter/group logic),
`DivisionTabs`, `TeamCard` (the playoff-spot boundary logic), `PlayerPage`
(the "came from leaderboard vs. roster" back-navigation logic, via a real
`MemoryRouter`), and `ErrorFallback`/`Sentry.ErrorBoundary` (confirms a
render error is actually caught instead of white-screening). Not yet
covered: `StandingsPage`/`RosterPage`/`StandingsTable`/`RosterPanel`/
`TrendChart` — a good next batch to add.

## Error tracking

Optional, via [Sentry](https://sentry.io). Set `VITE_SENTRY_DSN` in
`.env` and `main.jsx` reports errors there; leave it unset and the app
runs normally with no error reporting. Either way, `main.jsx` wraps the
whole app in `Sentry.ErrorBoundary` with a fallback UI
(`src/components/ErrorFallback.jsx`) — a render error shows a "something
went wrong, reload" message instead of a blank white screen, whether or
not Sentry is actually configured to receive the report.

## Deployment

Deployed to Azure Static Web Apps via GitHub Actions
(`.github/workflows/azure-static-web-apps-*.yml`) on every push to `main`.
A `test_job` (runs this Vitest suite) gates `build_and_deploy_job` — a
failing test blocks the deploy.
