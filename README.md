# PuckPulse

**NHL scores, playoff odds, and tonight's lines next to fair odds. Free.**

PuckPulse is a full-stack hockey app with two layers:
- **A fan app:** live scores and box scores, standings, playoff odds, goal alerts, team and player pages.
- **A betting-research layer:** each game's moneyline, puck line, and total from the sportsbooks next to PuckPulse's own fair odds, plus projected goalies and lineups. Every prediction is graded against the closing line.

It's backed by its own models: an expected-goals model, a team rating and playoff simulator, a score-distribution model, and starting-goalie projections. Each one is backtested on past seasons before it ships.

**Live:** https://puckpulse.io (installable as a phone app)

*Formerly "NHL Dashboard"; the repo and Azure resources keep their original names. Data from the
NHL and The Odds API. Not affiliated with or endorsed by the NHL. Betting
information is for entertainment and research, not advice. 21+. Gambling problem? Call
1-800-GAMBLER.*

## What it does

**Games**
- **Scores:** today's games with live period and clock, any day of the season from a calendar,
  and NHL.com recaps and highlights.
- **Box scores:** linescore, scoring summary, three stars, team stats, and player stats.
- **Game previews:**
  - win probability
  - the Market view (the books' odds)
  - goalies' games in net
  - tonight's **projected lineups from NHL.com**, one team at a time: L1–L4, D1–D3, the
    projected starter, scratches, and injuries. Before it's posted, each team's last game,
    from shift charts.
- **Share cards:** a game's Share button gives a link (`puckpulse.io/g/{id}`) that previews in
  iMessage, Discord, or Reddit as a card with the matchup and win chances, or the score once
  it's on.

**Bets**: tonight's slate, one card per game.
- **Each bet:** moneyline (the best price at a state-licensed US book, named), puck line, and
  total.
- **Fair odds:** PuckPulse's fair price is currently 30% our model, 70% the market, until the
  model earns more weight against the closing line.
- **Value badge:** when the price returns +2% or more at fair odds, and the model leans that way.
- **Context:**
  - back-to-back flags
  - who's in net: NHL.com's projected starters once posted, else our projection
  - a plain-language how-to-read section
- **Totals are labeled beta** and never badged, because in testing they didn't beat a
  league-average guess.

**Season**
- **Standings:** by division, with playoff odds and an Advanced view (xG%, shots, PDO).
- **Playoff race:**
  - odds over the season
  - the points line to make it
  - why each team's odds are what they are
  - a season simulator for "what if they win their next 5?" scenarios
- **Team and player pages:**
  - season summary, roster, and lines
  - injuries and news
  - player bios, career history, and 5-on-5 stats
- **News:** NHL.com, ESPN, and Sportsnet headlines, plus injuries and transactions.

**Play along**
- **Beat PuckPulse:** a pick'em with no sign-up. Pick tonight's winners, climb a public
  leaderboard, and see if you can beat the model's picks.
- **Goal alerts:** Web Push for every goal and final in games your team plays, within a minute.

**PuckPulse AI**
- **A tool-calling agent** (`intelligence/`): ask questions on any page, answered only from the
  app's own data and models. It can run standings, schedules, scenario simulations, and odds
  explanations.
- **Free providers:** Gemini, with Groq as fallback.
- **An eval suite** checks its answers.

**App**
- Installable PWA with a bottom tab bar.
- Light and dark themes: it follows the system until you pick, with no flash on load.

## The models

All of them are graded out of sample, and the write-ups are in [`docs/LEARNING.md`](docs/LEARNING.md).

| Model | What it does | How well (out of sample) |
|---|---|---|
| **xG** (`xg_model.py`, `train_xg.py`) | Chance of each shot becoming a goal. Logistic regression with 41 features (distance, angle, shot type, rebounds, rushes, strength…), trained on 453k shots, 2022–26 | Ties MoneyPuck's shot-level xG on 2024-25. As team ratings, Brier 0.1093 vs 0.1104 with MoneyPuck's |
| **Team ratings + playoff odds** (`simulate_playoff_odds.py`, v2.6) | Ratings from goals and xG, shrunk toward a prior: a roster rating (the sum of the players) plus goaltending. 10,000 simulated seasons with official tiebreakers. The game model has home ice and back-to-backs (both nights fit on real games) | Playoff Brier 0.1095 over 4 backtested seasons (v2.1: 0.1167) |
| **Goal model** (`goal_model.py`) | The chance of every final score. Conway-Maxwell-Poisson goals with a shared component, tie inflation from score effects, empty-net goals by lead, and OT. Gives the moneyline, puck line, and total from one distribution, with the margin solved to match the win model | Puck line calibrated within 1–3 pts across 3 held-out seasons (5,248 games). Totals ≈ a league-average guess |
| **Projected goalies** (`goalie_starts.py`) | Each goalie's chance to start: recency-weighted starts, back-to-back rotation, current roster | The top pick started 65.6% of the time (78% on back-to-back nights) over 10,112 team-games, calibrated within a few points |

Some things were measured and **didn't** ship, because the data said no:
- aging curves (survivor bias)
- blending this season's goalie starts into the prior
- the starting goalie as a win-model input (it added nothing once back-to-backs were counted)

**The report card:** every morning's predictions are logged before any game starts and never
changed. `market_odds.py --report` grades them against the sportsbooks' morning and closing
lines, and against Kalshi. Early on, the books lead by about 0.008 Brier on moneylines, which is
why the Bets tab blends toward the market. It takes several hundred games to know for sure.

## Architecture

```
                      ┌────────────────────────── Azure ───────────────────────────┐
 Browser / PWA  ────► │ Static Web Apps (React + Vite)                             │
                      │   └─ managed function: /g/{id} share pages (link previews) │
                      │                                                            │
                      │ Container App: API (FastAPI, 0.25 CPU, 1 replica always)   │──► Postgres (Neon)
                      │ Container App: PuckPulse AI (intelligence/, scales to 0)   │      ▲
                      │ Container Apps Job: daily ingest, 2 AM ET ─────────────────┼──────┤
                      │ Function (Flex Consumption): live notifier + closing odds ─┼──────┘
                      └────────────────────────────────────────────────────────────┘
   Sources: NHL API (scores, play-by-play, shift charts, rosters) · NHL.com content API (lineups,
   news) · NHL stats API · The Odds API · Kalshi · ESPN/Sportsnet/RotoWire/DobberHockey news
```

- **Frontend:** React 19 + Vite on Azure Static Web Apps.
  - A Static Web Apps managed function serves `/g/{id}` share pages, since link previewers
    don't run JavaScript.
  - Strict CSP (`script-src 'self'`). The theme is set before paint from `public/theme-init.js`.
- **API:** FastAPI in a container on Azure Container Apps, with read-only database credentials
  and a short TTL cache.
  - Live scores and box scores come straight from the NHL API through a stale-while-error cache.
  - Everything else is served from Postgres.
  - It draws the share-card images with Pillow.
- **PuckPulse AI:** a separate FastAPI service. It reads only the API's public endpoints and
  never sees database credentials.
- **Daily ingest** (`run_daily_ingest.py`, a Container Apps Job at 06:00 UTC): standings,
  stats, xG, ratings and odds, predictions, goalie projections, market odds, the AI-written
  digest, rosters, lines, and MoneyPuck's odds, each step isolated so one failure doesn't stop
  the rest.
- **Notifier function** (`backend/notifier_function/`, Azure Functions Flex Consumption):
  - goal and final pushes every minute during game hours
  - a closing-odds snapshot about 15 minutes before puck drop
- **Database:** Postgres on Neon (serverless).
- **Cost:** about $12–13/month. The API's always-on replica is most of it; the free tiers
  cover the rest.

## Data pipeline

The daily job, in order (`backend/run_daily_ingest.py`):

| Step | What it does |
|---|---|
| `ingest_standings.py` | Today's standings, all 32 teams |
| `ingest_advanced_stats.py` | 5-on-5 Corsi/Fenwick/xG/PDO (team and skater) and goalie GSAx, from our per-game rows plus the NHL stats API |
| `ingest_xg.py` | PuckPulse xG for each finished game from NHL play-by-play, plus each team's starting goalie |
| `simulate_playoff_odds.py` | Team ratings and Monte Carlo playoff odds (v2.6) |
| `game_predictions.py` | Logs today's win probabilities and expected goals (write-once), and grades finished games |
| `goalie_starts.py` | Projected starting goalies for today's games |
| `market_odds.py` | Morning snapshot: sportsbook consensus (moneyline, puck line, total, best licensed prices) and Kalshi |
| `daily_digest.py` | The morning digest, written by PuckPulse AI from that day's facts |
| `ingest_player_stats.py` | Rosters and season stats; marks released players off-roster |
| `team_lines.py` | Each team's lines and D pairs from its last game, from NHL shift charts |
| `moneypuck_odds.py` | MoneyPuck's playoff odds, logged next to ours for a head-to-head |

Also:
- **Every minute** during game hours: `notify_live_games.py` (goal and final alerts; records
  results for pick'em).
- **Every 5 minutes:** `market_odds.log_closing()` (the closing line, a few Odds API calls a
  day).
- **On demand, cached:** NHL.com projected lineups (`projected_lineups.py`).
- **Offline tools:**
  - `backtest_playoff_odds.py`, `calibrate_playoff_model.py`
  - `backtest_goal_model.py`, `backtest_goalie_starts.py`
  - `train_xg.py`

## Engineering

- **Workflow:** feature branch → PR into `dev` → release PR `dev` → `main`, with merge
  commits. `main` deploys.
- **CI gates every deploy:**
  - backend pytest (about 440 tests)
  - frontend Vitest and ESLint (about 260 tests)
  - intelligence tests
- **Deploys verify themselves:** GitHub Actions with OIDC (no stored Azure password), and images
  on GitHub Container Registry.
  - After a backend deploy, the new revision has to be healthy *and* `/health` has to report
    the exact commit, or the deploy fails.
  - A daily drift check fails if production isn't running `main`.
- **Monitoring:**
  - Sentry (errors and real-user performance)
  - an Azure Monitor alert on any API crash
  - a healthchecks.io heartbeat on the daily job
  - Application Insights on the notifier function
- **Analytics:** Umami Cloud (cookieless; the tracker is self-hosted so the CSP stays strict).

## Data sources and credits

- **NHL:** `api-web.nhle.com` (scores, play-by-play, rosters, stats, schedules),
  `api.nhle.com/stats/rest` (shift charts; skater and goalie season stats for the player ratings
  and advanced stats), and NHL.com's content API (projected lineups, news).
  No key needed. Reference: https://github.com/Zmalski/NHL-API-Reference
- **MoneyPuck.com:** its published playoff odds, logged next to ours as a benchmark (not shown).
  Its season files are a fallback only if our goalie data for a past season is incomplete. Since
  2026-10, every number on the site is ours or the NHL's.
- **The Odds API:** sportsbook odds (`ODDS_API_KEY`, free tier: about 310 of 500 credits a
  month). Best prices are shown only from state-licensed US books.
- **Kalshi:** public market prices, logged and graded but not displayed.
- **ESPN and Sportsnet:** headlines, injuries, and transactions.

## Repo layout

```
backend/        FastAPI app, daily ingest, models, backtests, tests
  notifier_function/   Azure Function: goal alerts + closing odds
frontend/       React app (src/), Static Web Apps function (api/), PWA config
intelligence/   PuckPulse AI: the tool-calling agent, its tools, and evals
docs/           LEARNING.md: what was built, measured, and learned, with resume bullets
HANDOFF.md      Current state and what's next
```

## Local development

See [`backend/README.md`](backend/README.md), [`frontend/README.md`](frontend/README.md), and
[`intelligence/README.md`](intelligence/README.md).
