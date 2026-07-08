# NHL Stats Dashboard — Backend Starter

## What this is
The data layer for an NHL stats dashboard: a Postgres schema plus a script
that pulls current standings from the NHL's public API and stores a daily
snapshot. Snapshots let you chart trends over the season instead of only
ever showing "right now."

## Setup

1. Create a Postgres database (local, or a free-tier host like Neon/Supabase/Railway).
2. Run the schema:
   ```
   psql "$DATABASE_URL" -f schema.sql
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt --break-system-packages
   ```
4. Create a `.env` file:
   ```
   DATABASE_URL=postgresql://user:password@host:port/dbname
   ```
5. Run the ingestion script:
   ```
   python ingest_standings.py
   ```

Run it once a day (cron, Task Scheduler, or a scheduled Lambda later) to
build up history. Running it multiple times on the same day is safe —
it won't duplicate rows for a date that's already been captured.

## Data source
`https://api-web.nhle.com/v1/standings/now` — public, no API key needed.
Full reference: https://github.com/Zmalski/NHL-API-Reference

## API layer

`api.py` is a FastAPI service that reads from `standings_snapshots` and
serves it as JSON.

Run it locally:
```
uvicorn api:app --reload
```

Then visit:
- `http://127.0.0.1:8000/docs` — interactive API docs (auto-generated)
- `http://127.0.0.1:8000/teams` — list of teams
- `http://127.0.0.1:8000/standings/latest` — most recent standings, all teams
- `http://127.0.0.1:8000/standings/PIT` — full history for one team
  (add `?start=2026-01-01&end=2026-04-01` to filter by date range)

## Next steps (in order)
1. ~~Run this daily for a few days, confirm rows are landing correctly.~~ ✅ Done (scheduled task set up)
2. ~~Add a thin API layer (Flask/FastAPI) to query the data.~~ ✅ Done
3. Build 2-3 visualizations: standings trend line, Penguins' season record,
   a stat you care about.
4. Deploy simply first (Railway/Heroku), then layer in the "resume" infra
   pass — Docker, AWS, Terraform, scheduled Lambda ingestion.

## Notes
- `season_id` format is `20252026` for the 2025-26 season.
- `streak_code` is `'W'`, `'L'`, or `'OT'`; pair with `streak_count`.
- Standings snapshots are unique per `(snapshot_date, team_abbrev)`, so
  re-running the script the same day just no-ops on conflict.
