# NHL Stats Dashboard

A full-stack NHL analytics dashboard: live standings, team rosters, a
league-wide player leaderboard, 5-on-5 advanced stats (Corsi/Fenwick/xG%/PDO)
sourced from MoneyPuck, and a from-scratch Monte Carlo playoff-odds
simulation you won't find as a prebuilt feed anywhere else.

**Live:** https://ashy-sky-01e4eba1e.7.azurestaticapps.net

## What it does

- **Standings** — live NHL standings by division, with a season trend
  chart (daily points this season, or points across the last 5 seasons)
  and a playoff-odds percentage built right into the table.
- **Team drill-down** — click a team for a snapshot card (record,
  home/road split, division/conference/league rank), then its full
  roster split into forwards, defensemen, and goalies.
- **Player drill-down** — click a player for bio, season stats, career
  totals, season-by-season history, and 5-on-5 advanced stats (see below).
- **League leaderboard** — every rostered player, sortable by any stat,
  searchable, skaters and goalies split out.
- **Standings, sortable by advanced stat** — click CF%/xG%/PDO in the
  standings table to re-sort the league by that column, backed by a real
  `?sort_by=` query param on the API, not client-side-only sorting.
- **Playoff odds** — a from-scratch Monte Carlo simulation, not a
  third-party feed.

## Why some of this is harder than it looks

**Advanced stats (Corsi/Fenwick/xG%/PDO).** MoneyPuck's own site and
directory listings sit behind a Cloudflare bot-check demanding a paid data
license for scraping — but the individual CSV files under
`moneypuck.com/moneypuck/playerData/seasonSummary/{season}/regular/*.csv`
are not behind that check, confirmed by fetching them directly. This pulls
team- and skater-level 5-on-5 stats from those CSVs directly; PDO isn't a
column MoneyPuck publishes, so it's derived from the underlying
goals/shots columns. (An earlier version of this recomputed Corsi/Fenwick
from scratch out of the NHL API's own play-by-play + shift-chart data,
based on the mistaken assumption that MoneyPuck blocked all automated
access rather than just its website UI — replaced once the CSV endpoints
turned out to be open.) See
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
  via GitHub Actions (`.github/workflows/backend-deploy.yml`) on every
  push to `main` that touches `backend/`. Tests run first; the image is
  built in Azure Container Registry, tagged with the commit SHA, and
  rolled out to the API and the ingestion job.
- **Database** — Postgres on Neon (serverless).
- **Data ingestion** — standalone Python scripts, separate from the API
  process, scheduled via an Azure Container Apps Job (`nhl-standings-ingest`). The API only ever reads
  from Postgres; it never calls the NHL API directly, so a slow or
  unreachable upstream never affects the live site.

## Data pipeline

| Script | What it pulls | Schedule |
|---|---|---|
| `ingest_standings.py` | Daily standings snapshot, all 32 teams | Daily |
| `simulate_playoff_odds.py` | Monte Carlo playoff-odds simulation | Manual (being cleaned up) |
| `ingest_player_stats.py` | Full roster + season stats, all 32 teams; marks cut/released players off-roster | Daily |
| `ingest_advanced_stats.py` | 5-on-5 Corsi/Fenwick/xG%/PDO, team + skater, from MoneyPuck | Manual, ~weekly in-season |
| `backfill_season_history.py` | Last 5 completed seasons' final standings | One-time |

The daily scripts (standings, then player stats) run through
`run_daily_ingest.py`, the entry point of the `nhl-standings-ingest`
Container Apps Job (06:00 UTC).

## Tech stack

React 19 · Vite · FastAPI · psycopg2 · Postgres (Neon) ·
Docker · Azure Container Apps · Azure Static Web Apps · Azure Container
Registry · GitHub Actions · Sentry (error tracking)

## Local development

See [`backend/README.md`](backend/README.md) and
[`frontend/README.md`](frontend/README.md).

## Known limitations

- Both backend (pytest, `backend/tests/`) and frontend (Vitest + ESLint,
  `frontend/src/**/*.test.jsx`) gate their deploys — a failing
  test or a lint error blocks the deploy on either side. The backend
  deploy also verifies itself: after `az containerapp update` reports
  success, it polls the new revision's own health state *and*
  `GET /health` for up to 4 minutes, and fails unless production reports
  the exact commit just deployed — added after a typo'd env var name
  once crash-looped every deploy for days while the old pipeline kept
  reporting green.
- Deploy drift: `GET /health` reports the commit the running image was
  built from, and a daily GitHub Action (`deploy-drift-check.yml`) fails
  if production isn't running main's latest backend commit. Added after
  the old Azure DevOps pipeline silently stopped triggering in July 2026
  and production ran July's code until October. Note that GitHub disables
  scheduled workflows in public repos after 60 days without activity —
  re-enable it from the Actions tab if that happens. See [`backend/README.md`](backend/README.md) and
  [`frontend/README.md`](frontend/README.md) for how to run these locally.
- Monitoring: Sentry (error tracking, optional —
  `SENTRY_DSN`/`VITE_SENTRY_DSN`) plus two Azure Monitor alerts, both
  emailing the same address — one on any container crash (scans
  `ContainerAppConsoleLogs` for a Python traceback), one on ingestion
  going stale (an hourly background check in `api.py` logs an error if
  `standings_snapshots` hasn't been updated in 30h, meaning
  the `nhl-standings-ingest` Container Apps Job has likely stopped running or is failing).
- Ingestion runs via an Azure Container Apps Job (`nhl-standings-ingest`) on a daily schedule, with its image kept in sync on each backend deploy — no longer a local Windows Task Scheduler job.

## Data source

Everything comes from the NHL's public API — no key required:
`api-web.nhle.com` (standings, rosters, player stats, play-by-play,
schedules) and `api.nhle.com/stats/rest` (shift charts). Reference:
https://github.com/Zmalski/NHL-API-Reference
