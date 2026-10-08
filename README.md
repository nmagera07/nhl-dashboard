# NHL Stats Dashboard

A full-stack NHL analytics app: live scores and box scores, standings with
a from-scratch Monte Carlo playoff-odds model, team and player pages, a
league leaderboard, 5-on-5 advanced stats from MoneyPuck, and an AI chat
("NHL Intelligence") grounded in the app's own data. Installable on phones
as a PWA.

**Live:** https://ashy-sky-01e4eba1e.7.azurestaticapps.net

## What it does

- **Scores** — today's games with live period/clock, finals, and start
  times; browse any day of the season from a calendar that only offers game
  days. Every game opens a full box score: linescore, scoring summary, three
  stars, team stats, and per-team player stats.
- **Standings** — by division, with logos, playoff odds, and an Advanced
  view (xG%, shots, PDO) sortable server-side via `?sort_by=`.
- **Team pages** — a season summary (record, splits, ranks, playoff status)
  above the full roster.
- **Player pages** — bio, this season, career totals, season-by-season
  history, and 5-on-5 advanced stats.
- **Leaderboard** — every rostered player, sortable and searchable.
- **Playoff odds** — a Monte Carlo simulation with regressed team ratings,
  a game model calibrated on ~4,000 real games, and official tiebreakers;
  backtested against past seasons (see `docs/LEARNING.md`).
- **NHL Intelligence** — ask questions on any page; answers come only from
  the dashboard's own data for that page (`intelligence/`).
- **Phone app** — installable PWA with a bottom tab bar.

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
  built on the runner, pushed to GitHub Container Registry (public)
  tagged with the commit SHA, and rolled out to the API and the
  ingestion job.
- **NHL Intelligence** — a separate FastAPI service in `intelligence/` that
  builds compact, page-specific summaries from the dashboard's public API
  and asks an LLM to answer from them only. It never sees database
  credentials. Currently on Google Cloud Run (moving alongside the API).
- **Database** — Postgres on Neon (serverless).
- **Data ingestion** — standalone Python scripts, separate from the API
  process, scheduled via an Azure Container Apps Job (`nhl-standings-ingest`).
  Standings, rosters, stats, and odds are served from Postgres, so the
  NHL API is never in the path for those pages. Live scores, box scores,
  and the game calendar come from the NHL API through a short-lived cache
  (`backend/nhl_games.py`): seconds for live games, an hour for finished
  ones; concurrent requests share one upstream fetch; and if the NHL API is
  down, the last good copy (up to 6 hours old) is served instead of an
  error.

## Data pipeline

| Script | What it pulls | Schedule |
|---|---|---|
| `ingest_standings.py` | Daily standings snapshot, all 32 teams | Daily |
| `simulate_playoff_odds.py` | Monte Carlo playoff odds (v2: regressed goal-differential ratings, calibrated game model, NHL tiebreakers) | Daily |
| `ingest_player_stats.py` | Full roster + season stats, all 32 teams; marks cut/released players off-roster | Daily |
| `ingest_advanced_stats.py` | 5-on-5 Corsi/Fenwick/xG%/PDO, team + skater, from MoneyPuck | Manual, ~weekly in-season |
| `backfill_season_history.py` | Last 5 completed seasons' final standings | One-time |

The daily scripts (standings, playoff odds, then player stats) run
through `run_daily_ingest.py`, the entry point of the
`nhl-standings-ingest` Container Apps Job (06:00 UTC).
`calibrate_playoff_model.py` and `backtest_playoff_odds.py` are offline
tools for tuning the playoff model (see their docstrings).

## Tech stack

React 19 · Vite · FastAPI · psycopg2 · Postgres (Neon) ·
Docker · Azure Container Apps · Azure Static Web Apps · GitHub Container
Registry · GitHub Actions · Sentry (error tracking)

## Local development

See [`backend/README.md`](backend/README.md),
[`frontend/README.md`](frontend/README.md), and
[`intelligence/README.md`](intelligence/README.md).

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
  `SENTRY_DSN`/`VITE_SENTRY_DSN`, not yet enabled in production), an
  Azure Monitor alert on any API crash (`nhl-api-startup-crash`, scans
  `ContainerAppConsoleLogs` for a Python traceback and emails via the
  `nhl-api-crash-alert` action group), and a healthchecks.io heartbeat
  on the daily ingestion job (`run_daily_ingest.py` pings start /
  success / fail via `HEALTHCHECK_URL`; healthchecks.io emails if a run
  fails, runs long, or never happens). The heartbeat replaced an Azure
  log alert on the API's hourly `STALE_INGESTION` check, which still
  logs but no longer pages anyone.
- Ingestion runs via an Azure Container Apps Job (`nhl-standings-ingest`) on a daily schedule, with its image kept in sync on each backend deploy — no longer a local Windows Task Scheduler job.

## Data source

Everything comes from the NHL's public API — no key required:
`api-web.nhle.com` (standings, rosters, player stats, play-by-play,
schedules) and `api.nhle.com/stats/rest` (shift charts). Reference:
https://github.com/Zmalski/NHL-API-Reference
