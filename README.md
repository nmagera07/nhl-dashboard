# NHL Stats Dashboard

A full-stack NHL analytics dashboard: live standings, team rosters, a
league-wide player leaderboard, and two stats you won't find prebuilt
anywhere else — 5-on-5 Corsi/Fenwick computed from raw play-by-play data,
and a Monte Carlo playoff-odds simulation.

**Live:** https://ashy-sky-01e4eba1e.7.azurestaticapps.net

## What it does

- **Standings** — live NHL standings by division, with a season trend
  chart (daily points this season, or points across the last 5 seasons)
  and a playoff-odds percentage built right into the table.
- **Team drill-down** — click a team for a snapshot card (record,
  home/road split, division/conference/league rank), then its full
  roster split into forwards, defensemen, and goalies.
- **Player drill-down** — click a player for bio, season stats, and
  5-on-5 Corsi/Fenwick (see below).
- **League leaderboard** — every rostered player, sortable by any stat,
  searchable, skaters and goalies split out.
- **Playoff odds** — a from-scratch Monte Carlo simulation, not a
  third-party feed.

## Why some of this is harder than it looks

**Advanced stats (Corsi/Fenwick).** The usual sources for this data
(MoneyPuck, Natural Stat Trick) both block automated access — MoneyPuck's
Cloudflare check demands a paid license for scraping, and Natural Stat
Trick's `robots.txt` explicitly disallows AI-agent user agents. Instead
of working around that, this computes the same stat directly from the
NHL's own public API: for every 5-on-5 shot attempt, it cross-references
the event's timestamp against every player's on-ice shift intervals for
that period to figure out who was actually on the ice. See
[`backend/ingest_advanced_stats.py`](backend/ingest_advanced_stats.py).

**Playoff odds.** A real Monte Carlo simulation, not a lookup: for each
remaining game, a logistic win-probability model (based on point
percentage, with a home-ice adjustment) picks a winner, accounting for
the NHL's loser-point rule on games that go to overtime/shootout. 10,000
simulated seasons → each team's odds of making the 16-team playoff field.
Backtested against a completed season and correctly called 26 of 32
teams' playoff fate at a >50% threshold — the two misses both had real
second-half surges no January-form model could have predicted. See
[`backend/simulate_playoff_odds.py`](backend/simulate_playoff_odds.py).

## Architecture

```
React (Vite)  ──>  FastAPI  ──>  Postgres (Neon)
     │                 │
Azure Static      Azure Container
  Web Apps            Apps
```

- **Frontend** — React + Vite, deployed to Azure Static Web Apps via
  GitHub Actions on every push to `main`.
- **Backend** — FastAPI, containerized, deployed to Azure Container Apps
  via Azure Pipelines on every push to `main` that touches `backend/`.
  A test stage runs the pytest suite first; the build/push/deploy stage
  only runs if it passes.
- **Database** — Postgres on Neon (serverless).
- **Data ingestion** — standalone Python scripts, separate from the API
  process, scheduled via Windows Task Scheduler. The API only ever reads
  from Postgres; it never calls the NHL API directly, so a slow or
  unreachable upstream never affects the live site.

## Data pipeline

| Script | What it pulls | Schedule |
|---|---|---|
| `ingest_standings.py` | Daily standings snapshot, all 32 teams | Daily |
| `simulate_playoff_odds.py` | Monte Carlo playoff-odds simulation | Daily |
| `ingest_player_stats.py` | Full roster + season stats, all 32 teams | Manual, ~weekly in-season |
| `ingest_advanced_stats.py` | Corsi/Fenwick from play-by-play + shift data | Manual, ~weekly in-season |
| `backfill_season_history.py` | Last 5 completed seasons' final standings | One-time |

## Tech stack

React 19 · Vite · Recharts · FastAPI · psycopg2 · Postgres (Neon) ·
Docker · Azure Container Apps · Azure Static Web Apps · Azure Container
Registry · GitHub Actions · Azure Pipelines

## Local development

See [`backend/README.md`](backend/README.md) and
[`frontend/README.md`](frontend/README.md).

## Known limitations

- Backend has a pytest suite (`backend/tests/`), gated in CI before
  deploy. Frontend has no automated tests yet.
- The NHL's legacy shift-chart endpoint (used for advanced stats) is
  missing data for roughly a third of games league-wide — a gap in the
  NHL's own data, not something fixable on this end. The player card
  surfaces this transparently rather than hiding it.
- Ingestion scripts run manually or via a local Windows Task Scheduler,
  not a cloud-native scheduler — fine for a personal project, would move
  to something like Azure Functions on a timer trigger for anything
  beyond that.

## Data source

Everything comes from the NHL's public API — no key required:
`api-web.nhle.com` (standings, rosters, player stats, play-by-play,
schedules) and `api.nhle.com/stats/rest` (shift charts). Reference:
https://github.com/Zmalski/NHL-API-Reference
