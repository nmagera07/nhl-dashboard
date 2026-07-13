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

Current coverage: `useFetchWithStatus` (the shared fetch/loading/error
hook), `LeaderboardPanel` (sort/filter/group logic), `DivisionTabs`,
`TeamCard` (the playoff-spot boundary logic), and `PlayerPage` (the
"came from leaderboard vs. roster" back-navigation logic, via a real
`MemoryRouter`). Not yet covered: `StandingsPage`/`RosterPage`/
`StandingsTable`/`RosterPanel`/`TrendChart` — a good next batch to add.

## Deployment

Deployed to Azure Static Web Apps via GitHub Actions
(`.github/workflows/azure-static-web-apps-*.yml`) on every push to `main`.
