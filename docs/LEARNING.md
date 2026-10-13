# Learning Log

What I've learned building this project: what happened, why it matters,
and how I'd describe it on a resume or in an interview. Newest first.

---

## Resume bullets

Ready-to-use lines, grouped by theme. Details for each are in the entries below.

**CI/CD and reliability**
- Traced a missed push notification across every hop (detection, database claim, job logs,
  push service) to Android's idle batching plus a short expiry; fixed with high-urgency
  delivery, per-event expiry, and per-device delivery logging.
- Migrated backend CI/CD from Azure DevOps to GitHub Actions with OIDC
  federated identity, removing every stored cloud credential from the pipeline.
- Added post-deploy verification (the new revision must be healthy *and* report
  the exact commit just deployed) plus a daily deploy-drift check, after finding
  production had silently run three-month-old code.
- Cut API database latency ~9x (0.53s → 0.06s per request) by finding a per-request connection,
  3 cross-country round trips per query, and uncompressed 1.15 MB responses; fixed with pooling,
  autocommit and gzip, plus a cross-request cache, cold-start warm-ups, offline-capable saved
  data, streamed AI answers, and Sentry real-user monitoring.
- Introduced a `dev` → `main` promotion workflow with branch protection and
  required frontend and backend test checks on every PR.

**Cloud and cost**
- Launched the app on a custom domain (puckpulse.io): DNS ownership validation (TXT), apex
  and www CNAMEs with Cloudflare CNAME flattening, auto-renewing managed TLS on Azure Static
  Web Apps, and CORS updates across two services, verified end to end in a browser.
- Moved container images from Azure Container Registry to GitHub Container
  Registry with a zero-downtime expand → migrate → contract migration,
  cutting monthly hosting costs by ~87%.
- Consolidated daily data ingestion into a single scheduled Azure Container
  Apps Job with failure isolation between steps and automatic retry.

- Replaced a log-based Azure alert with a heartbeat monitor (healthchecks.io)
  that also detects a scheduled job that never runs, and cut the monthly
  Azure bill from ~$11.44 to ~$0.97.

**AI engineering**
- Built a write-once prediction log for a live model: every game prediction stored before
  puck drop with its model version and inputs, graded automatically after the final, and
  scored by favorite win rate, Brier score vs. a coin flip, and calibration, served by a
  public API.
- Added an explanation tool to an LLM agent ("why is X favored over Y?") and used evals to find
  how models misread tool output (flipped directions, ambiguous field names, guessed team names);
  fixed it with pre-interpreted, self-describing results, raising the fallback model's pass rate
  from 50% to 83%.
- Fixed stale answers from an AI agent by moving its schedule tool from a daily snapshot to
  live data and giving the model today's date and Eastern start times.
- Shipped a daily AI-written digest as a batch job (one LLM call a day, shared by all users),
  with facts computed by code, AI keys confined to one service, and a facts-only fallback.
- Built an eval suite for an LLM agent: live ground truth from the app's API, tool-use and
  argument checks, a made-up-number (grounding) detector, and a cross-provider LLM judge;
  it caught a hallucination and a tool-calling bug on day one (10/12 and 9/12 → 12/12).
- Turned an LLM chat into a tool-calling agent over the app's data and its Monte
  Carlo model: the model chooses the query, deterministic code produces every
  number, so "what if" and "what does this team need" answers are grounded.
- Designed the agent around free-tier limits: measured prompt tokens per round,
  cut the default context from ~4,200 to ~1,100 tokens, and cached simulations,
  so multi-step questions fit a free provider's per-minute budget.
- Rebuilt an LLM chat feature to run on free providers (Gemini → Groq) with
  automatic failover, cutting AI cost to $0 after the paid key ran out;
  evaluated models against ground-truth questions (hosted 5/5 vs. local 7B 3/5).
- Cut LLM context from ~1.3M characters (98% silently truncated) to ~3.4K
  measured tokens of purpose-built summaries, so answers became correct and
  free tiers became viable.

**Security**
- Ran a full security audit (gitleaks over history, pip-audit/npm audit, Semgrep/Bandit, manual
  review): shipped a strict browser-tested Content-Security-Policy, pinned all CI actions to commit SHAs
  with least-privilege tokens, pinned dependencies, and added prompt-injection guards for the LLM agent.
- Designed push notifications with SSRF protection (only real push-service
  endpoints accepted) and least-privilege database access (the API can write
  one table; the signing key lives only in the notifier's secrets).
- Removed a write-capable database credential that was exposed as a plain-text
  environment variable on the API, enforcing least privilege (the API only
  holds a read-only credential, stored as a secret).

**Data and modeling**
- Rebuilt a Monte Carlo playoff-odds model (regressed team ratings, game
  model calibrated on ~4,000 real games, official tiebreakers) and validated
  it by backtesting against 3 past seasons: 15% lower Brier score overall,
  29% lower in early season.
- Added expected-goals (xG) data to the model and proved the gain with
  leave-one-season-out backtesting on as-of data (no lookahead): a further
  3.7% lower Brier overall and 7.6% early in the season.
- Made the model's preseason prior roster-aware (last season's strength plus the value of
  players gained minus players lost), backtested over 4 seasons: 2.6% lower Brier overall,
  4.9% on Nov 1, never worse at any checkpoint; caught and fixed a data gap where the NHL's
  roster feed dropped injured players, which had counted a team's best forward as departed.
- Found that the model's expected-goals prior contained no goaltending at all (xG measures
  shots, not saves) and added each team's goalie strength (GSAx, shrunk for its 0.16
  year-to-year repeatability): 1.9% lower Brier again, better than the previous model in
  every backtested season.

- Built an in-browser season simulator by porting the Monte Carlo model to
  JavaScript, validated against the Python original over 10,000 simulated
  seasons (mean gap 0.5 percentage points, the noise floor); runs ~7,000
  full seasons per second client-side at zero server cost.
- Found and fixed a date-boundary bug that silently dropped each day's games
  from the daily playoff simulation (about half the league simulated one game
  short, every day), with a regression test.
- Diagnosed why our playoff odds differed from MoneyPuck's by 16 points for one team (a goals
  vs. expected-goals blend and different priors) and turned the question into a measurable
  head-to-head through prediction logging.
- Built a per-team "why these odds?" explanation for a Monte Carlo model: each rating split
  into additive parts (goals, xG, last season) that sum to it exactly, plus schedule strength
  in the same units, computed daily and loaded on demand behind one tap.
- Built a trade simulator for a Monte Carlo playoff model: player values in goals/game over
  replacement from a box-score composite calibrated against 96 team-seasons (r = 0.86), with
  shrinkage for small samples, exposed to an LLM agent as a "what if they traded X?" tool.
- Tested three more model ideas (adjusted xG, strength of schedule,
  goaltending) with held-out backtests and shipped none after showing the
  gains were noise, e.g. goalie performance correlates only r ≈ 0.1 year to year.

**Frontend**
- Built a news aggregator (NHL.com, ESPN, Sportsnet headlines, injuries, transactions) with
  per-source caching and failure isolation, similarity-based dedupe of cross-outlet recaps, and
  LLM agent tools for injuries and news, caught and fixed a wrong-team lookup bug via evals.
- Added game highlights (recaps, condensed games, per-goal clips) by mining feeds the app
  already loaded, with link allowlisting and cache timing tuned to when the NHL posts videos.
- Built pregame previews (model win probability, form, ranked team stats, top goalies, season
  series) and a stale-while-revalidate cache so back navigation is instant while live data
  stays fresh.
- Designed and shipped the PuckPulse brand: explored logo directions as SVG at real sizes and
  in Android icon crops, built a full PWA icon set from one master SVG with a dark-mode variant,
  and fixed stale home-screen icons by cache-busting icon URLs.
- Rebranded the product (NHL Dashboard → PuckPulse) to avoid league trademark issues: vetted
  names for existing apps and open domains, changed every user-facing surface, and kept storage
  keys stable so users' saved settings survived.
- Replaced silent PWA updates with a prompted "new version ready" flow built on the
  service-worker lifecycle, with hourly checks, verified by simulating a release in a real
  browser.
- Built an interactive playoff race page with a hand-written responsive SVG
  chart (no chart library): hover and tap to follow a team, live readout,
  and a full prior season backfilled from as-of data for comparison.
- Built a personalized "My team" experience without accounts: a
  `useSyncExternalStore` preference hook keeps every component (and every
  open tab) in sync, with a team card showing live/next game, recent results,
  and playoff odds.
- Made heavy client-side computation feel instant by running 3,000 seasons in
  small slices so the histogram fills in live without freezing the page.

**Data and backend**
- Fixed a data-integrity bug where cut and released players stayed on team
  rosters indefinitely (~580 stale records), using a soft-delete flag that
  preserves player history.
- Rebuilt the live game box score by merging three NHL API endpoints in
  parallel, with graceful degradation when the optional feeds fail.

---

## 2026-10-13 — Goalies: the prior had no goaltending in it at all

**The insight:** the prior is last season's *xG* differential. xG is built from shots (where
they're from, what kind), so it describes the skaters. It says nothing about whether the
goalie stopped them. A team with Hellebuyck and a team with a replacement goalie got the same
prior. Before writing code, the question was what was missing, not what had changed.

**So I tested two versions:**
- *Change*: count goalie moves like skater moves (new tandem minus last season's).
- *Level*: add each team's current goalie strength in full, since none of it was in there.

The backtest settled it: *change* did nothing (0.1137 → 0.1137), and *level* helped
(0.1137 → 0.1115). The *change* version assumed the prior already had last year's goalie in
it. It didn't, so subtracting him was subtracting nothing.

**Goalie numbers are noisy, so measure that first:** GSAx per 60 has a year-to-year
correlation of just **0.16** (194 goalie pairs with 25+ games in both seasons). Most of a
great season is luck. Each goalie is pulled toward the regular-goalie average by 100
pseudo-games; a goalie with no NHL history counts as replacement level (fringe goalies run
−0.217 GSAx/60, a real gap).

**Picking the setting without fooling myself:** the top of the grid kept moving (weight 2.0,
shrink 25 scored best on average), and leave-one-season-out showed those picks overfitting:
0.1631 on a held-out season vs. 0.1424 for skaters alone. So I fixed the weight at 1.0,
because GSAx is already in goals, and chose the shrink by season-by-season table, not the
average. Shrink 100 beats v2.1 in **all 4 seasons** and v2.2 in 3 of 4, and it fixes the
one season (2023-24) where roster moves alone made things worse.

**Today's effect:** Tampa +8 (Vasilevskiy), Washington +8 (Logan Thompson), Pittsburgh −14
(Silovs plus a rookie), Ottawa −8.

**Lessons:**
- *Ask what a number contains.* "Last season's strength" sounded complete; xG made it
  skaters-only. The fix came from reading the definition, not from more data.
- *When the best setting is the most extreme one, check whether it holds up on new seasons.*
  A flat surface plus moving picks means noise, so pick the principled value.
- *Per-season tables catch what averages hide.* The 2025-26 regression was invisible in the
  overall mean.

**Interview framing:** "My preseason prior was built on expected goals, which only measure
shots, so goaltending wasn't in the model at all. I measured how repeatable goalie numbers
are (barely: r = 0.16), shrank them to match, and backtested 'goalie changes' against 'goalie
level'. Only level helped, which confirmed the diagnosis. Then I chose the setting from a
per-season table rather than the overfit top of the grid."

## 2026-10-13 — Scoring against the best: logging MoneyPuck's odds next to ours

**Why:** every backtest so far compared the model with older versions of itself. The real
question is whether it beats MoneyPuck, the public model most fans trust. The only honest way
to know is to log both *before* the results are known and score them at the end, the same
write-it-down-first rule as the game prediction log.

**What:** a daily job step pulls MoneyPuck's published simulation CSV (one row per team per
next-game scenario; "ALL" is the unconditional odds) and stores it in `moneypuck_odds`.
`moneypuck_odds.py --report` prints how far apart the models are now, and Brier scores for
both once the season is decided.

**The detail that matters: line dates up by information, not by clock.** MoneyPuck updates at
~4:30 AM ET, and our job runs at 2 AM ET. Both have seen the games through yesterday, so
MoneyPuck's update on day D is stored as day D. Our 2 AM job picks it up the next night,
since theirs comes out after ours. If I'd stamped it with the fetch date, every comparison
would give MoneyPuck's odds one extra day of results.

**Small call:** a MoneyPuck outage logs a warning and skips the day instead of failing the
job. A failed run retries every step and pages me, too much for one missing data point.

**Day 1:** the models differ by 8 points per team on average. MoneyPuck is more spread out
(Dallas 87% vs our 63%). In April we'll know which spread is right.

## 2026-10-13 — Roster-aware priors: last season's team isn't this season's team

**The problem:** in October the model leans on last season. With 3 games played, about 90%
of a team's rating is last season's xG differential, halved. So a team that lost three
top-six forwards in the summer was rated like the team that had them, and a team that
signed two good ones got no credit until the games caught up (by midseason).

**What changed (model v2.2):** the prior is now *last season's strength + roster moves*.
Every skater already has a value in goals/game over replacement (the trade simulator's
`player_values.py`). For each team: add the value of skaters who arrived, subtract the
value of those who left, each weighted by how much of last season he played (a regular
who leaves costs more than a call-up). Players who stayed cancel out. Rookies and players
from Europe count as replacement level (0), which is the honest default with no NHL data.

**How I knew it was better (backtest first, then ship):**
- 4 seasons x 5 checkpoints, as-of data (values use only the two seasons *before*, so no
  peeking). Compared against the live v2.1 model, not just the old goals-only one.
- Weight grid 0 to 1.5. The best was **1.0**: the player values work at face value, with
  no fudge factor. That's a good sign the trade-simulator calibration (r = 0.86 against
  team goal differential) was right.
- Results: 2.6% lower Brier overall; Nov 1: 0.1551 → 0.1475 (4.9%); never worse at any
  checkpoint; leave-one-season-out better on 3 of 4 held-out seasons.
- Known leak, documented: MoneyPuck lists a traded player under his *last* team, so in the
  backtest deadline deals leak in slightly. Most moves are summer moves, and the gain is
  biggest in November, before the deadline.

**The bug the dry run caught:** before shipping I ran today's model without saving and
listed the players behind the biggest swings. Carolina was the second-biggest "loser",
because Seth Jarvis and Alexander Nikishin "left for no team". They hadn't: the NHL's
`roster/current` feed leaves out injured reserve, and our `on_roster` flag comes from it.
The player landing endpoint has `currentTeamAbbrev` (set for injured players, empty for
retired or unsigned ones: Kopitar, Tarasenko), so the model now looks up any missing
regular big enough to matter (29 players, ~6 seconds). Carolina went from "lost 0.28
goals/game" to about even.

**Lessons:**
- *Read the rows, not just the summary.* The backtest number was fine; the bug only showed
  up when I asked "which players make up this −0.28?".
- *A feature's data source can mean something narrower than its name.* "Current roster"
  meant "active roster", and that's fine for a roster page but wrong for a season prior.
- *Reuse the unit.* Because player values and team ratings were built in the same unit
  (goals/game), the roster prior was ~30 lines plus a backtest, not a new model.

**Interview framing:** "In October, my model was mostly last season's team. I folded in
roster moves using player values I'd already calibrated for a trade simulator, backtested
it against the live model on four seasons without lookahead, and the best weight was 1.0,
so the values held up at face value. Early-season error dropped 5%. A dry run then caught
injured players being counted as departures, which came down to the NHL's roster feed
meaning 'active roster'."

## 2026-10-11 — A security audit: scanners first, then the parts scanners can't see

**What I ran:**
- **gitleaks** over all 171 commits of history. No secrets were ever committed, and the local `.env` files
  are git-ignored.
- **pip-audit** and **npm audit** on every service's dependencies.
- **Semgrep** (Python, JavaScript, React, secrets, GitHub Actions) and **Bandit**.
- A manual review of what scanners can't judge: write endpoints, auth, CORS, the AI's inputs, and the
  headers the site sends.

**What was actually wrong (and fixed):**
- **No Content-Security-Policy and no frame protection** on puckpulse.io. I crawled every page type in a real
  browser to list the outside hosts the app really uses (the NHL image server, our two APIs, Sentry).
  Then I wrote a strict policy and **tested it enforced against the live site** before shipping it:
  zero violations, with the chat, charts, and logos all working. Added `X-Frame-Options: DENY`, a
  Permissions-Policy, and COOP.
- **GitHub Actions referenced by movable tags** (`actions/checkout@v4`). A compromised or re-tagged action
  would run inside the deploy jobs that can sign in to Azure. I pinned all 28 references to commit SHAs
  and added GitHub Actions to Dependabot so the pins stay current.
- **Four workflows had no `permissions:` block**, so they got the default token rights. They now get
  read-only access (plus PR comments for the preview deploy).
- **The AI service's dependencies were version ranges**, so each Docker build could pick up an untested
  release. They're pinned like the backend's now. That also moved pytest past PYSEC-2026-1845, and the
  newer pytest-asyncio cut test warnings from 475 to 6.
- **Dev-tool advisories** (brace-expansion, source-map-js, both build-time only) were fixed with
  `npm audit fix`.
- **Defense in depth:** news links must be `https://`. The AI is told that tool results (outside headlines,
  injury notes) are data, never instructions, which is a prompt-injection guard now that outside text
  reaches it. The API sends `nosniff`.

**What the scanners flagged that was fine** (and why that matters):
- Two "SQL built from strings" warnings: both only use values from fixed allow-lists.
- "curl piped to shell": it's piped to a JSON parser, not a shell.
- "Untrusted XML": Python's Expat (2.7) blocks entity-expansion bombs.
- gitleaks "5 leaks" in a full-disk scan: the git-ignored local `.env` files, never committed.

Triage is the skill. A scanner's output is a to-do list, not a verdict.

**What I learned:**
- Test a security control the way you'd test a feature. A CSP that breaks the site gets turned off, so
  enforcing it in a browser before shipping is what makes it stick.
- The biggest risks were in configuration (headers, CI permissions, action pinning), not in the code.
- Untrusted text reaching an LLM is an input-validation problem. Label it as data, and keep the tools
  read-only so even a successful injection can't do much.

**Interview angle:** "How would you security-review an app?" Automate the cheap scans (secrets, dependencies,
SAST), triage every finding, then review by hand what tools miss: auth, data flow into the LLM,
headers, and the CI/CD supply chain. Verify each fix doesn't break the product.

---

## 2026-10-11 — A cleanup pass you can prove changed nothing

**What I did:** Paid down the duplication that piled up during a fast day of features:
- Split the 1,400-line `App.css` into 21 files by area (`src/styles/`).
- Replaced several copies of the same small helpers with one shared version each: 3 copies of
  `ordinal()` ("22nd"), 4 date formatters ("Oct 9"), and 2 signed-number formatters ("+1.5" / "−0.3").
- Fixed the last lint warning in the fetch hook.
- Moved the season-id helpers the backend scripts shared into one `seasons.py`.

**The interesting part, proving "no visible change":**
- **CSS order is behavior.** Later rules win ties, so splitting a stylesheet can quietly change how
  the page looks. I kept each file a contiguous range of the original, imported in the original order.
- **I compared the built output, not the source.** I captured the production CSS bundle before
  and after and diffed it rule by rule. The only difference was 4 rules I deliberately moved into the
  scores file, after checking that nothing they could collide with comes later. Everything else was
  byte-identical.
- **The lint fix kept the same behavior.** The hook's effect must only refetch when the URL changes,
  but it read callbacks that change on every render. Keeping the latest callbacks in a ref satisfies
  the rule without refetching on every render.

**What I learned:**
- Behavior-preserving refactors need an oracle. For CSS, the built bundle is a good one. For code,
  it's the test suite (all 571 tests passed before and after).
- One shared formatter is also a consistency fix. Two copies of "signed number" had already drifted
  (one handled missing values, one didn't).

**Interview angle:** "How do you refactor safely?" Pick something you can compare before and after
(built output, tests, screenshots), keep the steps mechanical, and explain any intended difference.

---

## 2026-10-11 — News: aggregating sources you don't control

**What I built:** A News tab with headlines (NHL.com, ESPN, Sportsnet), injuries, and transactions. The
three freshest headlines also show on Scores, and each team page gets its own headlines and injury
report. PuckPulse AI got `get_injuries` and `get_news` tools, so "is he injured?" finally has a real
answer instead of "I don't have that information."

**What I checked before building:**
- **An X (Twitter) feed:** X's official embed loaded in a real browser but showed "Rate limit
  exceeded" to logged-out visitors and pulled 420 KB of scripts. The API has had no free tier for new
  developers since February 2026; reading posts is pay-per-use. Parked, and social media is a later
  decision.
- **Feeds:** I probed eight candidates. NHL.com's own RSS returns 403. The feeds nhl.com and ESPN's
  apps use internally work, but they're undocumented, so the code assumes they can break.

**Problems the real data exposed:**
- **RSS timestamps can lie.** ESPN's RSS feed stamps every item with the feed's build time, so all
  its headlines read "1m ago" and sorted to the top. I switched to ESPN's JSON feed, which has a real
  publish time per article (and flags ESPN+ paywalled stories, which I skip).
- **The same game recap three times.** On game nights NHL.com, ESPN, and Sportsnet all run
  near-identical recaps ("Kraken overcome Ovechkin's first goal of season, edge Capitals" / "...to beat
  the Capitals 5-3"). Exact-title matching missed them. Word overlap (Jaccard) on content words
  (filler and scores removed) separates them cleanly: the same story scores ~0.7, different angles on
  the same game score ~0.4 or less, with the cutoff at 0.6.
- **The AI guessed teams.** Asked "Is Drew Helleson injured?", the fallback model looked up the wrong
  team's injury report and answered "not listed", which reads as "healthy". The eval caught it. The
  tool now searches the whole league by player name, and "not on the report" never means "healthy".

**Design decisions:**
- **Each source fails on its own.** Each one is cached separately (about 15 minutes) and keeps its last
  good copy for up to a day, so one feed breaking never breaks the page.
- **Headlines and facts only, always linking out**, with the source named. We never copy the article.
- **Kept the page uncluttered:** injuries collapse to one row per team ("Anaheim Ducks · 5"), with
  your team open.

**What I learned:**
- With data you don't own, verify every field against reality. A timestamp field existing doesn't mean
  it's correct.
- Deduplication is a similarity problem, not an equality problem.
- "Not found" and "no" are different answers. Tools should say which one they mean.

**Interview angle:** "How would you build a news aggregator on sources you don't control?" Isolate each
source (its own cache, timeout, and stale fallback), normalize timestamps and teams, dedupe by
similarity, attribute and link out, and test against live data, because that's where the surprises are.

---

## 2026-10-11 — Making it fast: measure, find the real bottleneck, repeat

**Why:** People leave if an app makes them wait. I asked Grok to review the app's speed, then
checked every claim against the code and the live API before changing anything.

**What the measurements found (in the order I found them):**
1. **A new database connection on every request.** Opening a Neon connection costs ~0.5s (TLS +
   auth). `/health`, just `SELECT 1`, took 0.78s against 0.25s for a route with no database.
   Fix: a small connection pool behind the one `get_connection()` function, so none of the 19
   call sites changed. It throws away connections idle over 4 minutes, because Neon drops them
   at ~5.
2. **No compression.** `/players/leaders` was 1.15 MB of JSON. With gzip it's 83 KB.
3. **The database and the API are on opposite coasts.** The DB is in AWS us-east-1 (Virginia)
   and the API in Azure West US 2 (Washington), so every round trip crosses the country. On top
   of that, psycopg2's implicit `BEGIN` plus the pool's `ROLLBACK` meant **3 round trips per
   query**. Switching to autocommit (safe for a read-only API) made it one.
   Result: `/health` went from 0.78s to 0.30s, and the database part from 0.53s to ~0.06s.
4. **The AI service opened a new HTTPS connection for every API call** and re-downloaded
   once-a-day data on every question. Fix: one keep-alive client plus a 10-minute cache.
5. **Cold starts (~20–30s) are the real worst case.** Three cheap fixes: opening the chat
   wakes both services in the background; once-a-day data is saved in the browser, so return
   visits render in ~0.1s even with the API down (tested by blocking every API request); and
   the Playoffs chart no longer waits on the standings.
6. **Streaming answers.** It now works end to end, and it taught me something. Timing each
   phase showed Gemini starts writing ~0.6s into the answer round and finishes ~0.3s later, so
   streaming only saves ~0.3s here. Its bigger payoff is with slower models and longer answers.
   The phase timing also showed the slow runs I'd seen (5–6s) came from Gemini's free-tier rate
   limit pushing questions to the slower fallback model, not from the code.

**Chat today (warm):** "Who leads in points?" went from 3.3s to ~2.1s. "Why are PIT's odds so
high?" went from 5.3s to ~1.8s, with the first words at ~1.4s.

**Real-user monitoring:** Sentry was installed on the frontend but never turned on in
production (no DSN at build time). It's now on, with Web Vitals, API timings, and a custom
span per chat answer (time to first status, first text, total). Next decisions (static
data files, moving the database west, paying for always-on) will use real numbers.

**What I learned:**
- Measure each phase, not just the total. "The chat is slow" was really four separate costs:
  connection setup, cross-country round trips, cold starts, and provider rate limits.
- The biggest wins were boring: a pool, gzip, one autocommit flag. None needed a redesign.
- Know your infrastructure's geography. One cross-country round trip is ~70 ms; three per
  query, on every request, adds up.
- Free tiers have two hidden costs: cold starts and rate limits. Both show up as "slow".

**Interview angle:** "How would you speed up a slow app?" Measure first and break the time down
by phase, fix the cheapest big costs (connections, compression, round trips, caching), hide
the costs you can't remove (warm-ups, saved data), and add real-user monitoring so the next
call is based on data.

---

## 2026-10-11 — A trade simulator: putting a player and a team on the same scale

**What I built:** PuckPulse AI can now answer "what if Detroit traded Larkin?". Each skater
gets a value in **goals per game over a replacement-level player**. That's the same unit as
the playoff model's team ratings, so a trade is just arithmetic: the team losing the player
drops by his value, the team getting him gains it, and the season simulation re-runs both
ways. A new agent tool (`simulate_roster_change`) handles:
- "traded for an unknown return" (his minutes go to a replacement-level player)
- "traded to Toronto"
- "Larkin for Matthews"
- "out for the season"

**First numbers (2026-10-11):**
- Larkin gone: Detroit drops from 38% to 29%.
- McDavid to Detroit: Detroit goes from 38% to 60%, and Edmonton drops from 83% to 67%.
- Larkin for Matthews: about a wash.

**The dead end first:** I started with *relative 5-on-5 xG* (on-ice minus off-ice expected
goal differential). It's a respected stat, but used alone it rated Crosby, Makar and Larkin
*below average* and put third-pair defensemen in the league's top 12. It misses finishing,
the power play, and deployment (stars play against other stars). I caught it with an eye test
on known players before building anything.

**What worked:** Game Score, a public box-score composite (goals, assists, shots, blocks,
penalties, faceoffs, on-ice shots and goals), then:
- **Calibrated to our units:** across 96 team-seasons, team Game Score per game predicts goal
  differential per game at r = 0.86, and the slope (0.194) converts Game Score to goals.
- **Replacement level from data:** the Game Score of fringe players (5–29 games), separately
  for forwards and defensemen.
- **Shrinkage:** this season and last are blended and pulled toward replacement level by 10
  pseudo-games, so a hot week doesn't create a star (the same idea as the team ratings).
- The result passes the eye test (MacKinnon +0.29, McDavid +0.27, Larkin +0.12) and matches
  the scale of public WAR models (roughly 20–25 goals a season for the very best).

**Limits I put in the tool's own output:** skaters only (no goalies), line-mates and team
quality leak into on-ice numbers, an incoming player is assumed to replace a replacement-level
one, and it ignores chemistry and the salary cap. The AI is told to call it a rough estimate.

**What I learned:**
- A model gets much easier to extend when everything shares one unit. Picking "goals/game" for
  team ratings months ago is what made player values plug in cleanly.
- Sanity-check a metric against things you already know before you build on it. A respected
  stat can still be the wrong tool for a specific question.
- Calibrate borrowed formulas to your own target instead of trusting their scale.

**Interview angle:** "How would you estimate the impact of a trade?" Put players and teams in
the same unit (goals over replacement), calibrate that against real team results, shrink small
samples, re-run the simulation, and be upfront about what it ignores.

---

## 2026-10-11 — PuckPulse AI learns "why": shaping tool output so models can't misread it

**What I built:** A new agent tool, `explain_odds`, so PuckPulse AI can answer "why are
Pittsburgh's odds so high?" and "why is Carolina favored over the Rangers?". It returns the
same breakdown as the Playoffs page (goals, xG, last season, schedule). With two teams, it
also compares them and gives the model's win probability for their next meeting. Two new
eval cases check these answers against live data.

**What the evals caught**, even though the first version picked the right tool and the
right team every time:
- **A backwards read.** One model said PIT's +5 goals on even xG meant "the scoring isn't a
  fluke." It means the opposite: scoring above your chances usually cools off.
- **Misread fields.** `easiest_rank: 16 of 32` became "the easiest schedule in the league."
  `per_game: 0.799` became "0.799 points per game." `share_of_rating_pct: 83` became "last
  season is most of the reason," when it's actually how much the model *trusts* last season,
  not how much it *moves* the rating.
- **Wrong team names.** With only abbreviations, Groq called the Penguins "the Panthers" and
  the Sabres.
- **Truncation.** A table-heavy answer hit the token cap mid-sentence.

**The fixes were all in the tool's output, not the prompt:**
- Every factor carries a spelled-out `push` ("pushes up" / "pulls down" / "negligible"), so
  the model never has to interpret a sign or decide what's small.
- The goals-vs-xG reading is computed in code and stated in a sentence.
- Fields describe themselves: `rank: "16th easiest of 32"`, `xg_diff_per_game`,
  `weight_vs_this_season_pct`, and full team names.
- One instruction line: answer in 3 to 5 bullets, no tables.

Groq went from 1 of 2 to 5 of 6 passing runs, and Gemini passed every run.

**What I learned:**
- Tool output is a user interface whose user is a language model. Ambiguous field names get
  misread the same way a confusing UI label does.
- Do interpretation in code wherever you can (directions, thresholds, what a gap means). The
  model's job is the wording.
- An LLM judge is only as good as its rubric. Twice it failed correct answers because the
  rubric didn't say a point was allowed. Read the failing answers before "fixing" anything.

**Interview angle:** "How do you reduce hallucination in a tool-using agent?" Make the tools
return pre-interpreted, self-describing facts, then measure with evals that read the
answers, not just the tool calls.

---

## 2026-10-11 — "Why these odds?": explaining a model in four lines

**What I built:** On the Playoffs page, tapping a team now opens a short breakdown under its
row: why its odds are where they are. Each of four lines says which way it pushes (▲ pushes
up / ▼ pulls down / – little effect):
- **Goals:** this season's goal differential.
- **Expected goals:** this season's xG differential (shot quality).
- **Last season:** last year's strength and how much of the rating it still is (83% six
  games in; it fades as games are played).
- **Schedule:** how strong the remaining opponents are, plus the home/away balance.

**Why:** The MoneyPuck question (entry below) took me a manual deep dive to answer. Now the
app answers it for anyone: the Penguins' +5 goals push them up, their xG is dead even, and
last season still carries most of the rating.

**Design decisions:**
- **An explanation that adds up.** The rating is a weighted average, so I split it into
  three parts (goals, xG, last season) that sum to the rating exactly, with a test that
  checks it. There's no approximate "feature importance" here.
- **Same units everywhere.** All four factors are in goals/game, including the schedule
  (opponents' strength vs. a typical schedule, plus home ice), so they can be compared
  directly.
- **Computed once a day, not per request.** The daily job saves the breakdown with the
  simulator inputs. The endpoint just reads it.
- **Hidden by default.** The page looks the same for people who just want standings. The
  breakdown only downloads the first time someone opens a team.
- **Honest wording.** My first version called a schedule "one of the tougher ones" because it
  ranked 22nd. In October, though, every schedule is within 0.03 goals/game of average. I
  switched the wording to the size of the effect, not the rank.

**What I learned:**
- Explainability is easiest when it's designed into the model's math. A simple, additive
  model can explain itself exactly, while a black box needs approximations (like SHAP).
- A rank always sounds meaningful, even when the gaps behind it are tiny. Check the
  magnitude before writing the words.

**Interview angle:** "How would you explain a model's prediction to a non-technical user?"
Break it into parts that add up to the answer, in one unit, with plain-English direction
words, and keep it one tap away instead of on every screen.

---

## 2026-10-11 — A track record for the model: write once, grade later

**What I built:** Every game the model predicts is now logged and graded. Each morning
at 2 AM ET, the daily job saves every game on that day's slate with the model's
home-win probability, both teams' ratings, and the model version, before any puck
drops. It then grades earlier predictions once they're final (score, regulation, OT or
shootout, and who won). An API endpoint turns that into a scorecard.

**Why:** I asked why MoneyPuck had the Penguins at 45% to make the playoffs and we had
them at 61% (entry below). The honest answer was "nobody knows yet." The only way to
know is to write predictions down *before* the games and score them *after*. Backtests
had already shown the model was good on past seasons. This is the live version: it
proves the model keeps working on games it has never seen.

**Design decisions:**
- **Write once.** A logged prediction is never updated (`ON CONFLICT DO NOTHING`), so
  re-running the job can't quietly swap in a "better" prediction after the fact.
- **Skip when inputs are stale.** If that morning's odds run failed, nothing is logged.
  Logging yesterday's ratings as today's prediction would be dishonest.
- **Backfill only real predictions.** The morning digest had already stored genuine
  pre-game odds for two days. I backfilled those 17 games, marked `source='digest'`. I
  didn't backfill earlier days, because rebuilding "what the model would have said"
  afterwards risks leaking information the model couldn't have had.
- **Scoring logic is a pure module** (`prediction_record.py`), separate from the job's
  database code, so the API doesn't import the daily job and the math is easy to test.

**The metrics:**
- **Favorite win rate:** how often the team the model favored won. It's easy to grasp,
  but it ignores confidence.
- **Brier score:** the mean of (probability − outcome)². A coin flip scores 0.25 and
  lower is better. It rewards being confident *and* right, and punishes confident and
  wrong. Good hockey models land around 0.23–0.24, because single games are close to
  coin flips.
- **Calibration:** group predictions by confidence ("said 60–65%") and check how often
  they happened. A model can have a good Brier score and still be over-confident;
  calibration shows that.

**First numbers:** 14 graded games, the favorite won 10 of 13 (plus one 50/50 call),
Brier 0.221. That's a lucky start on a tiny sample. The 60–65% bucket went 4-for-4 and
the only 65%+ pick lost. It takes a few hundred games before the buckets mean anything.

**What I learned:**
- This is the same mindset as the AI eval suite: decide how you'll measure success,
  capture ground truth automatically, and don't trust a number you can't check.
- Data integrity is a design choice: immutability and provenance (the `source` and
  `model_version` columns) are what make a track record believable.
- Small samples lie. Report the sample size next to every metric.

**Interview angle:** "How do you know your model works in production, not just in
backtests?" Log predictions before outcomes exist, grade them automatically, and track
calibration as well as accuracy.

---

## 2026-10-11 — Why MoneyPuck says 45% and we say 61%

**Question I asked:** MoneyPuck had the Penguins at 44.9% to make the playoffs; PuckPulse
said 61%. What's different?

**What I found** by breaking down our Penguins rating:
- They were 3-2-1 with a **+5 goal differential** but **even expected goals**
  (0.0 xGD): they'd finished their chances and gotten saves at a better-than-expected
  rate.
- Our model blends goals and xG 50/50 (the blend won the backtest), so half the rating
  came from that +5. A model that leans harder on xG treats it as luck that will fade.
- Our starting point is last season's xG, which was decent for Pittsburgh.
  Serious models often start from the **current roster** (age, who left, who
  arrived), which probably rates an older Penguins team lower.

**What I learned:**
- Early in the season, every model is mostly its assumptions: six games is almost no
  data. Models disagree most in October and converge as results pile up.
- Two good models can disagree a lot about one team and still both be well calibrated
  overall. One team's number isn't a verdict on the model.
- The way to settle it is a track record (entry above), not an argument.
- Next modeling lever: roster-aware starting points (priors).

---

## 2026-10-11 — Highlights: using data that was already there

**What I built:** a "▶ Recap" button on every finished game on the Scores page, a
Highlights card in the box score (3-minute recap and condensed game), and a "▶ Watch"
link next to every goal.

**How:** I checked the NHL's feeds before planning anything. Goal clips were already in
the box score data the app loads; recaps were on the daily score feed. The gamecenter
feeds only had bare video IDs, which nhl.com can't open, so the links come from the score
feed, which carries the full URL paths. No new API, key, or cost.

**Decisions:**
- **Link out instead of embedding.** Playing the NHL's videos inside the app would mean
  using its video player in a way the NHL doesn't publicly offer. Linking to its
  public share URLs is clearly fine. It's a product trade-off made for legal reasons.
- **Cache with the data's timing in mind.** Finished games were cached for an hour, but
  recaps get posted a while after the final horn, so a cached "no recap" would hide the
  link for up to an hour. Recent finals without a recap now recheck every 5 minutes.
- **Allowlist links.** Only `https://nhl.com/video/...` URLs are ever rendered, so bad
  upstream data can't put a strange (or `javascript:`) link in front of users.
- **Accessible markup.** Links can't go inside buttons, so the recap link sits next to the
  card's button, not inside it.

**What I learned:** look at the real data before designing. The feature I expected to
need a new integration was already sitting in responses the app was downloading.

---

## 2026-10-11 — Game previews, and back navigation without a reload

**Game preview:** before puck drop, a box score used to be empty. Now it shows a
preview: win probability from our model (labeled "a lean, not a lock", and not betting
advice), division standing and playoff odds, last-10 form, team stats with league ranks,
players to watch, each team's top goalie, and the season series. Most of it comes from the
NHL's own pregame feeds, merged into the same box-score response.

**Back navigation:** going from a box score back to Scores reloaded the whole page
(empty cards, loading messages). I added a small **stale-while-revalidate** cache: show
the last response immediately, refresh in the background, and swap in the new data.
Live scores stay live, and going back shows 3 cards and 0 loading messages instead of 0
cards and 2 loading messages.

**What I learned:**
- Stale-while-revalidate is the right pattern for "fast but fresh" data, and it's the
  same idea behind HTTP's `stale-while-revalidate` header and libraries like SWR and
  React Query.
- A shared in-memory cache needs resetting between tests, or results leak from one test
  into the next.

---

## 2026-10-11 — A logo, and why the old icon wouldn't go away

**What I made:** The PuckPulse logo, a hockey puck with a heartbeat line across it and a
white rim. I explored four directions first (drawn as SVG and reviewed at real sizes, in
Android's icon crops, and in the header), then picked a ChatGPT concept and rebuilt it as
vector with a dark-mode version, since the original was designed for white and would
vanish on the app's near-black background.

**How:** One master SVG generates everything: the 512 and 192 app icons (sized for
Android's "maskable" circle and rounded-square crops), Apple's 180px home-screen icon, the
browser-tab icon, and the header mark next to a "Puck/Pulse" wordmark. Light and dark logo
PNGs for my resume and LinkedIn live in `design/`. I rendered the PNGs with headless
Chromium (the same engine phones use) because there was no image tool installed.

**The bug after shipping:** my phone still showed the old graph icon, even after
reinstalling. The server was fine (new icons, 30-second cache). Two caches on the device
held the old one:
- **The service worker's offline cache:** the old version keeps serving its saved
  icon and manifest until the new version takes over, which waits for the user to
  tap Refresh.
- **Android's installed-app copy:** the icon is baked in at install and refreshed only
  occasionally, keyed by the icon's URL.

**The fix:** new file names (`icons/puckpulse-512.png`, etc.) that no cache has ever seen,
while the old names also carry the new art for installs that still point at them. It's the
same idea as the content-hashed filenames bundlers use for JS and CSS, applied to icons.

**What I learned:**
- Design at the real sizes: a logo that looks great big can turn to mush at 16px, and
  Android crops icons into circles.
- Design for the background it'll actually sit on (dark mode).
- "Deployed" isn't "on the user's device": caches keyed by URL keep serving the old file,
  and a new filename is the reliable way to bust them.

**Interview angle:** "A user still sees the old version after your deploy. Why?" Caching
layers (CDN, browser, service worker, the OS), and cache-busting by changing the URL.

---

## 2026-10-10 — PuckPulse: a real name, a real domain

**What happened:** Renamed the app from "NHL Dashboard" to **PuckPulse** and put it on
its own domain, **https://puckpulse.io**, with HTTPS.

**Why rename:** "NHL" is a league trademark. Using it in a product name is fine for a
side project, but it's the kind of thing that draws a takedown once real people use it.
Fan apps use their own name and credit the data. The footer now says "Data from the NHL
and MoneyPuck.com. Not affiliated with or endorsed by the NHL."

**Picking the name:** I checked each candidate for an existing hockey app and for open
domains before falling for it. "Rinkside" was already a live hockey app (and every good
domain was taken), and "FrozenEdge" collided with the NHL's own "NHL EDGE" stats brand.
PuckPulse was clear, and "pulse" fits an app about live scores, alerts, and moving odds.

**The rename itself:** Everything users see changed (title, header, installed-app name,
"Ask PuckPulse", notifications). Internal names (repo, Azure resources, saved-setting keys)
stayed on purpose: renaming them means redeploying for no visible benefit, and changing
the storage keys would have wiped everyone's followed team.

**Putting it on puckpulse.io (DNS, refreshed):**
- **TXT record:** Azure gave me a random token to publish on the domain, proving I own
  it, so nobody else can attach my domain to their site.
- **CNAME records:** `puckpulse.io` and `www` are *aliases* for the app's Azure hostname,
  rather than A records pointing at an IP, so they follow Azure if it moves the site.
- **CNAME flattening:** DNS rules don't allow a CNAME on the bare domain. Cloudflare
  resolves it behind the scenes and answers with the final IP, which is why the bare
  domain works without a "www" redirect.
- **Proxy off ("DNS only"):** with Cloudflare's proxy on, Azure would see Cloudflare
  instead of itself and couldn't validate the domain or issue the certificate.
- **CORS:** the API and the AI service only accept requests from known sites, so both
  needed the new origins (one in code, one in the Container App's settings), plus a test
  that unknown origins stay blocked.

**Result:** both names validated and got free, auto-renewing TLS certificates (DigiCert,
via Azure Static Web Apps). I verified it in a real browser on the new domain: data loads,
the AI answers, and no requests fail.

**Lesson:** browsers treat a new domain as a brand-new site. Saved settings and push
subscriptions belong to the old address, so users re-install, re-pick their team, and
re-enable alerts. Worth knowing *before* a domain move, and worth telling users.

**Interview angle:** "Walk me through putting an app on a custom domain." DNS record
types, ownership validation, apex CNAME flattening, managed TLS, and CORS.

---

## 2026-10-10 — "A new version is ready": taking control of app updates

**The problem:** After a release, the installed app kept showing the old version.
The morning digest card didn't appear until I'd closed and reopened the app, sometimes
twice.

**Why:** A PWA's service worker serves the cached app instantly, then downloads the new
version in the background. With "auto update", the new version only takes over on a
*later* launch, so users never know an update exists.

**The fix:** Prompted updates. The new version downloads and *waits*, and a banner says
"🏒 A new version of NHL Dash is ready. [Refresh]". Tapping Refresh activates it and
reloads. The app also checks hourly, for sessions left open all evening.

**What I learned:**
- **The service-worker lifecycle** (install → waiting → activate) is the core of PWA
  updates; "skip waiting" is the switch between silent and prompted updates.
- **Test the real behavior, not just the component:** I simulated a release in a real
  browser (load v1, build v2, watch for the banner, tap Refresh, confirm the new bundle).
  My first fake release didn't work because the build strips CSS comments, so v2 was
  byte-for-byte identical to v1. Make sure the test actually exercises what you think it does.
- **A process lesson:** I reverted a test change with `git checkout` and wiped
  uncommitted work along with it. Commit before running tests that modify files.

**Interview angle:** "How do you ship updates to a PWA?" The service-worker lifecycle,
prompted vs. silent updates, and how I tested it end to end.

---

## 2026-10-10 — The chat gave a "next game" that had already happened

**The bug:** The evening after a Penguins game, I asked the chat when they play next, and
it named the game they'd just finished.

**Why:** The schedule tool read the playoff model's *morning snapshot*, refreshed at 2 AM ET.
By evening, a game the snapshot called "upcoming" was over. That's the exact window when
people ask. The model also didn't know today's date, so "next" and "tonight" were guesses.

**The fix:** The schedule tool reads the live NHL schedule (cached about a minute on game
days); "what if they win their next 4" skips games finished since the snapshot; every
question includes today's date in Eastern time; start times are in Eastern ("7:00 PM ET").
I also added `tzdata` after noticing the time-zone conversion could break on a slim server
image while passing every test locally.

**What I learned:** Know each data source's freshness. A daily snapshot is right for the
playoff model and wrong for "what's next". And an AI agent's answers are only as current
as its tools, plus whatever it's told about "now".

---

## 2026-10-10 — The missed final-score notification

**The bug:** No alert came when the Penguins' shootout loss ended, even though goal
alerts were turned on.

**Tracing it end to end:** The database showed the final was detected and claimed within a
minute. The job's logs showed "Sent 2 notifications" with no errors, so Google's push
service had *accepted* them. They were lost after that.

**Why:** I sent alerts at the default "normal" urgency with a 10-minute expiry. Android
holds normal-urgency messages while the phone is idle and delivers them in batches. Held
long enough, they expire, and Google silently drops them.

**The fix:** High urgency on every alert (wakes the phone), finals valid for 3 hours and goals
for 15 minutes, and the push service's response logged per device so a missing alert can be
traced. A test script sends a real alert on demand; it arrived on my Android phone within
seconds.

**What I learned:** "Sent" isn't "delivered". Push delivery has hidden policies (urgency,
TTL, battery saving), and logging each hop is what turns "it didn't work" into a diagnosis.

---

## 2026-10-10 — The morning digest: batch AI that costs the same for 2 users or 2,000

**What I built:** A "☀️ Morning digest" card on the Scores page: last night's results
and standouts, the biggest playoff-odds moves, and tonight's game of the night with the
model's win probability, written up by AI once a day.

**How:** The daily job (2 AM ET, after every game ends) gathers the **facts with code**:
finals, multi-goal and 3-point nights from the scoring summaries, odds moves between the
last two simulations, and tonight's games with the same win-probability model as the odds.
It sends them to NHL Intelligence's private `/digest/write` endpoint (shared-secret
header, constant-time comparison), stores the text and the facts, and the page shows it.
If the AI is down, the page shows the facts as a list instead.

**Design decisions:**
- **One AI call a day, shared by everyone:** the cost doesn't grow with visitors.
- **The AI keys live in one service:** the job asks NHL Intelligence to write; it never
  holds provider keys itself.
- **Graceful degradation:** facts are stored either way, so the card never goes empty.

**What I learned:**
- **Grounded isn't the same as correct.** Groq's first digest had every number right
  and the headline wrong: "Blue Jackets edge *Blues* in a shootout" (they beat the
  Penguins; the Blues game was that night). The made-up-number check passed. Fixes: a
  tighter prompt (headline about last night only, never mix last night and tonight), and
  an eval case where a judge checks every claim against the facts.
- **Reasoning models need room to think, and evals settle the trade-off.** Groq's gpt-oss
  returned nothing on the digest: it spent the whole token budget thinking. Turning reasoning
  effort to low fixed the empty output, but the evals then caught it getting things wrong:
  Crosby's PDO read backwards in chat, a shootout called "overtime", and the Blue Jackets
  turned into the Sabres. The fix was a bigger output budget at the default effort. Without
  evals I'd have shipped the "fix" that made answers worse.
- **Do the precise parts in code, again:** instead of making the model translate team
  abbreviations, the facts include ready-made lines ("Blue Jackets 3, Penguins 2 (SO)").
  It rephrases; it can't mislabel.
- **Give the model the context it lacks:** a headline said "Saturday's action" for Friday's
  games, and another called October "a late-season surge", until the facts included last
  night's date and season progress (games played of 84).
- **Judges need precise rubrics too:** a judge failed a correct digest for "missing games"
  the digest was told to leave out. Rubric fixed: omissions are fine; wrong claims fail.

---

## 2026-10-10 — An eval suite for the AI agent (and what it caught on day one)

**What I built:** `intelligence/evals/`: 12 real questions run through the agent
exactly as the app would run them, on each free provider, and scored automatically.
Each question's correct answer is computed live from the app's API at eval time
(standings and schedules change daily, so hardcoded answers would rot).

**Four kinds of checks:**
- **Tool:** did "what if PIT wins its next 4" call `simulate_scenario` with team=PIT, games=4, wins=4?
- **Facts / number:** does the answer contain the right team, date, scorer, record, or percentage?
- **Grounded:** every percentage in the answer must appear in what the tools returned
  (or be the difference between two of them). That's an automatic made-up-number detector.
- **Judge (LLM-as-a-judge):** a *different* provider grades fuzzy rubrics, like
  "did it read a PDO of 96 as bad luck?" or "did it admit it has no injury data?"

**First run: Gemini 10/12, Groq 9/12. After fixes: 12/12 on both.** What it found:
- **A real hallucination:** asked "Is Crosby injured?", Gemini said "he is not listed
  as injured", inferring health from data it doesn't have. Fixed with an explicit
  instruction: no injury/lineup/transaction data, say so.
- **A real robustness bug:** Groq's model called `get_leaders` (no arguments) with
  junk like `{"": ""}`. Sometimes Groq rejected the turn (HTTP 400
  "tool_use_failed"); sometimes my tool runner crashed on it. Fixes: drop unknown
  arguments, retry a malformed tool call once, and give the tool a real optional
  argument so the model has something valid to send.
- **Two bugs in my own eval:** the judge fell through to a small local model that
  misgraded a correct answer (and Groq's reasoning model needed a bigger output budget
  to grade at all), and a correct "8‑2" failed because the model used a non-breaking
  hyphen. A bad eval is worse than none, so I read every failure before believing it.

**What I learned:**
- Evals catch what unit tests can't: the code worked; the *behavior* was wrong.
- Compute ground truth from the source of truth, not hardcoded expectations.
- Deterministic checks first (cheap, never wrong), judges only for what rules can't check,
  and never let a model grade its own answers.
- Read the failures. Two of my first four "AI failures" were eval failures.

**Picking a model with evals instead of vibes (later that day):** after Groq's small
`gpt-oss-20b` kept stumbling, I ran the same suite on the two bigger models my free Groq key
offered. `gpt-oss-120b`: 13/13 on a confirmation run (12/13 the first time; its one miss was a
missing caveat). `qwen3.8-27b`: no quality misses, but it hit Groq's per-minute token cap twice,
which is risky for a *backup* that gets used exactly when traffic spikes. Switched to the 120b.

**Interview angle:** "How do you know your AI feature works?" An eval suite with live
ground truth, tool-use and grounding checks, a cross-provider judge, and a before/after
record showing it caught a hallucination.

---

## 2026-10-10 — NHL Intelligence becomes an agent (tool calling)

**What I built:** The chat used to get one page's data and answer from it. Now
it's an **agent**: it gets tools (standings, schedules, schedule strength,
playoff odds history, players, and the playoff-odds model's simulations) and
decides which to call. "What if Pittsburgh wins its next 4?" runs 2,000
simulated seasons and comes back with 59.7% → 72.8%. "What does Detroit
need?" returns its odds for every record over the next 10 games.

**The key design rule:** the model decides *what to ask*; deterministic code
produces *every number*. The LLM never estimates odds itself, so answers are
grounded in the same model that powers the rest of the app.

**What broke, and what I learned:**
- **Gemini's thought signatures:** Gemini picked the right tool every time,
  then rejected the follow-up with HTTP 400. Newer Gemini models attach a
  hidden "thought signature" to each tool call and require it back with the
  result. The fix: echo tool calls exactly as received. Provider "OpenAI
  compatibility" has edges.
- **Token budgets are architecture:** Groq's free tier caps tokens per
  minute, and every tool round resends the conversation. I measured it: the
  league page data was 3,300 of the 4,200 tokens per request, and redundant once
  the model could fetch standings itself. Sending a 150-token summary instead
  made multi-step questions fit.
- **Consistent answers to the same question:** the "what does Detroit need"
  table first came from seasons where Detroit *happened* to win more, which
  are also seasons where it happened to be rated better, so it disagreed with
  the "what if" tool. I switched it to forced results so both tools answer
  the same question the same way.
- **Model quality varies:** asked about Crosby, Gemini correctly read a PDO of
  91.9 as bad luck; Groq's model called it "close to average." That's exactly
  what an eval suite should catch automatically, which is the next step.

**Interview angle:** "Have you built an AI agent?" Yes: tool calling over real
data and a simulation engine, multi-provider failover, a token budget I
measured and designed for, and grounding (the model never makes up numbers).

---

## 2026-10-09 — Push notifications: goal alerts on your phone

**What I built:** "🔔 Goal alerts" on the My team card. Your phone gets a
notification for every goal in your team's games and the final score, and
tapping it opens the box score.

**How it works:**
- **Web Push:** the browser subscribes through its push service (Google,
  Apple, Mozilla, Microsoft) and hands back a private endpoint plus
  encryption keys. The server signs messages with a VAPID key pair and
  encrypts them so only that device can read them.
- **The watcher:** a Container Apps Job runs every minute during game hours,
  reads the NHL's live scoreboard (one request covers every game), and turns
  new goals and finals into notifications. Cost stays inside Azure's free
  allowance, versus ~$5-10/month for an always-on worker.
- **No duplicates:** each event is claimed in the database
  (`INSERT ... ON CONFLICT DO NOTHING RETURNING`) *before* sending, so
  overlapping runs or a crash mid-send never double-notify.

**Security decisions:**
- The server POSTs to whatever endpoint a subscription names, so the API only
  accepts real push-service hosts. Otherwise someone could register an
  internal URL and use the notifier to make requests (SSRF).
- The API's database role stays read-only except for the one subscriptions
  table. The private signing key only exists as a secret on the notifier job.

**Tested for real:** a browser subscribed through Google's push service, the
server encrypted and sent a goal alert, and the service worker displayed it.

**iPhone gotcha:** Apple only allows push for web apps installed to the home
screen (iOS 16.4+), so the app explains that instead of showing a button
that can't work.

**Interview angle:** "Design a notification system": polling vs. push,
at-most-once delivery with an idempotency key, cost trade-offs, and SSRF
protection.

---

## 2026-10-09 — "My team": personalization without accounts

**What I built:** Follow a team (star on its team page, or a picker on Scores)
and the app leads with it: record, division place, playoff odds, the live or
next game, and the last 5 results. A star marks it in tables, and Standings
opens on its division.

**What I learned:**
- **`useSyncExternalStore`** is React's built-in way to read outside state
  (here, localStorage). Every component reading the favorite updates together,
  and a `storage` event listener keeps other tabs in sync too.
- localStorage can throw (private mode, blocked cookies), so every read and
  write is wrapped and the app still works without saving.
- **Testing found a real bug:** the card said "Pittsburgh plays tonight" but
  the scoreboard didn't show the game. The NHL's `score/now` feed keeps serving
  last night's games until late morning, so the Scores page labeled
  yesterday's finals as today. Fixed by asking for today's games by date.

**Interview angle:** "How would you add personalization without user
accounts?" Local preference, shared through one hook, synced across tabs.

---

## 2026-10-09 — Playoff race page: a hand-built SVG chart

**What I built:** A Playoffs tab showing every team's odds over the season as
a line chart (tap or hover to follow one team), plus the conference laid out
the way the playoffs work: division top 3s, wild cards, the cut line, weekly
change, and clinched/eliminated badges.

**What I learned:**
- **SVG by hand instead of a chart library:** about 150 lines for exactly what I
  needed, with no dependency. Measuring the container with `ResizeObserver`
  and drawing at real pixel size keeps labels readable on phones, where a
  scaled `viewBox` would shrink the text.
- **No hindsight in the backfill:** to show last season's race, I re-ran the
  model for each week using only the data available on that date (xG from
  the game-by-game file, cut off at each date).
- **Database changes come before the code that needs them:** the new clinch
  column had to exist before the release that writes to it.

**Interview angle:** "Have you built data visualizations?" Yes, from scratch,
responsive, interactive, and accessible.

---

## 2026-10-09 — Season simulator: Monte Carlo in the browser (and a bug it exposed)

**What I built:** A "Sim the season" button on team pages. Each click plays
out the rest of the regular season (all ~1,280 games, every team) and shows
your team's final record, playoff seed, and a game-by-game strip. In the
background it runs 3,000 more seasons to show the likely range of points.

**How:** The daily job saves the model's inputs (constants, each team's record
and strength rating, the remaining schedule) as one 44 KB JSON document. The
browser runs the simulation itself, a JavaScript port of the Python model, so
every click is instant and costs the server nothing.

**Proving the port is right:** I ran 10,000 seasons through both versions on the
same inputs and compared every team's playoff odds. The average gap was 0.5
percentage points, exactly what random noise predicts. The model's constants
come from the API with the inputs, so the two versions can't drift apart.

**The bug it exposed:** Building the inputs, I checked which games count as
"still to play" and found the daily odds run had been skipping that day's games
entirely. Standings for a date include that day's games once played, but the
job runs at 2 AM ET, before they're played, and the code treated every game
dated today as already done. About half the league was simulated one game
short, every day. Fixed: a game on the as-of date stays "remaining" until it has
a final score.

**Also learned:** the NHL season is 84 games starting in 2026-27 (new CBA). The
simulator's 84-game records caught my hardcoded 82-game points pace.

**Interview angle:** "How do you know your code is correct?" Two independent
implementations, compared statistically, plus checking the simulation's
output against reality (records that add up to the real schedule length).

---

## 2026-10-09 — Goaltending: the "voodoo" is real

**Question:** Goalies swing seasons, so should the model rate goaltending on
its own instead of lumping it into goal differential?

**What I checked first (before building anything):** whether goaltending
*repeats*. If saving more goals than expected early doesn't predict saving more
later, it's mostly luck and can't help a forecast. On MoneyPuck data since 2010:

| Stat | odd vs. even games | this season vs. next |
|---|---|---|
| Team goals saved above expected | 0.23 | 0.18 |
| Team finishing (goals above expected) | 0.17 | 0.22 |
| Team xG differential | 0.64 | 0.60 |
| Individual goalie, year to year | | 0.10 to 0.13 |

Even individual goalies barely carry over, and a 2 to 3 season track record
doesn't help much (0.13). Hockey analysts call goaltending "voodoo" for
this reason.

**Backtest:** split the blend into xG + finishing + goaltending with separate
weights. Best: give goaltending *less* weight (0.25 vs 0.5), Brier 0.1158 vs
0.1162, but the held-out test picked a different goaltending weight every
season (0, 0, 0.25, 0.5) and scored worse than plain xG (0.1204 vs 0.1190).
Shifting winners are noise. Didn't ship.

**What I learned:**
- Check whether a signal is *repeatable* before modeling it. A correlation
  check took minutes; a goalie-tracking pipeline would have taken days.
- Something can matter a lot *after the fact* (a hot goalie explains a season)
  and still be useless for *predicting* it.

**Interview angle:** "How do you decide whether a feature is worth building?"
Measure whether the signal persists first.

---

## 2026-10-09 — Adjusted xG: a clean null result

**Question:** MoneyPuck also publishes *adjusted* xG (corrected for score
effects and home ice, and/or for rebound "flurries"). Would a cleaner version
of xG make the playoff odds better?

**What I did:** Added an `--xg-measures` option to the backtest so all four xG
flavors run side by side through the same grid and leave-one-season-out test.

**Result:** No. Score/venue-adjusted xG tied raw xG (Brier 0.1161 vs 0.1162,
well inside the noise, and the same held-out score). Flurry adjustment was
slightly *worse* (0.1167), so rebound chances seem to carry real signal about
team strength. I didn't change production.

**What I learned:**
- Score effects mostly average out over a season, and the 50/50 blend with real
  goals already smooths the noise the adjustment targets.
- Two "don't ship" results in a row (strength of schedule, then this) say the
  model has gotten what it can from team-level season totals. The next gains
  need *new information* (goaltending, roster changes), not a polished version
  of the same numbers.
- Making experiments cheap to run is what makes null results cheap to accept.

**Interview angle:** "Tell me about an experiment that didn't work." I tested
it properly, it didn't beat what was live, so I kept the simpler model.

---

## 2026-10-09 — Playoff odds v2.1: the right new data beats more tuning

**What happened:** The diagnostics said tuning was maxed out and the
remaining error came from information the model didn't have. So I added
MoneyPuck's expected goals (xG), which measures the *quality* of chances
rather than whether they happened to go in.

**What I learned:**
- **No lookahead in backtests.** MoneyPuck's season files are full-season
  totals, and using them to "predict" November would leak the future. Their
  game-by-game file let me compute xG *as of* each checkpoint date, which is
  the only honest way to test it.
- **This one passed the bar strength of schedule failed:** 3.7% better
  overall, 7.6% better on Nov 1, better on held-out seasons, and the *same
  recipe* won in every leave-one-out fold (50% goals + 50% xG, last season's
  xG as the prior). Consistent winners are real; shifting winners are noise.
- **It helps exactly where theory says:** early in the season, when goals
  are noisy. By March, a team's actual goals have caught up with its chance
  quality, so xG adds nothing.
- **Design for the dependency failing:** if MoneyPuck is down, the
  simulator falls back to the goals-only model instead of failing the job.
- **Read the data license:** MoneyPuck is free for non-commercial use *with
  credit*, so the credit is in the UI (with a test so it can't disappear),
  and the downloader identifies itself honestly instead of posing as a browser.

---

## 2026-10-09 — Playoff odds v3: when the right answer is "don't change it"

**What happened:** Set out to improve the playoff model further *without* new
data. Built better diagnostics first: a calibration table, leave-one-season-out
testing, a wider tuning grid over 4 seasons, and a strength-of-schedule
variant. The finding: **the model was already about as good as this data
allows, so I didn't ship a "v3."**

**What I learned:**
- **Calibration:** bucket predictions and check reality. When v2 says 75%,
  about 75% of those teams make it; v1's "85%" teams made it only 71% of the
  time. A model can have a decent overall score and still be systematically
  overconfident, and calibration shows that.
- **Leave-one-season-out exposes overfitting.** Settings tuned on three
  seasons scored *worse* on the fourth (0.1244) than the existing fixed
  settings (0.1208). All the top settings were within 0.0005 of each other,
  which is noise. Past that point, more tuning just fits randomness.
- **Negative results are results.** Strength-of-schedule ratings are sound in
  theory, but measured about 0.3% better (noise) and no better under honest
  testing. So it's documented as an experiment, not shipped. Shipping it would
  have added complexity for nothing.
- **Know which lever is left.** With goals-only data the model is at its
  ceiling. Remaining error comes from information it doesn't have (shot
  quality, goaltending), so the next real gain needs new data (MoneyPuck xG),
  not more tuning.

**Interview angle:** "Tell me about a time you decided *not* to ship
something." Measured it honestly, found no real gain, kept it simple.

---

## 2026-10-09 — NHL Intelligence: free AI, real evaluation, less magic

**What happened:** The AI chat was broken: its paid OpenAI key ran out. I
didn't want to pay for an API, so we rebuilt it to run on free tiers, moved it
into this repo, and deployed it to Azure next to the API.

**What I learned:**
- **Check what you're actually sending.** The chat sent the model the raw
  JSON, cut off at 24,000 characters. For league questions that kept **2%**
  of the data: half the standings, no leaders, no playoff odds. So the model
  *couldn't* answer correctly. The fix was a compact, purpose-built summary
  per page, not a bigger model.
- **Measure tokens, don't estimate.** I guessed ~3,700 tokens with the
  "4 characters per token" rule. The real count was **5,752**, because JSON
  full of numbers packs tighter. That was over the local model's 4,096-token
  window, which *silently* drops the start of the prompt, instructions included.
- **Do the reasoning in code, give the model the conclusion.** Small models
  couldn't work out wild-card spots from two rank columns. Computing a plain
  `playoff_spot` ("Eastern wild card 2 (in)") made those answers correct.
  Cheap, deterministic code beats asking an LLM to do math.
- **Evaluate with ground truth.** Five questions with known answers, run
  against each model:

  | | Gemini Flash-Lite | Groq gpt-oss-20b | Local Qwen 7B |
  |---|---|---|---|
  | Correct | **5/5** | **5/5** | 3/5 |

  A 1B model confidently named the wrong overtime scorer even with the right
  answer in front of it. Model size matters for *reliability*, not just fluency.
- **Design for free-tier limits:** every free tier has caps, so the service
  tries providers in order and falls over to the next on a rate limit or
  outage. Keys have no payment method attached, so the worst case is "busy,"
  never a bill. Streaming can only switch providers *before* the first word.
- **Separate service, same repo:** the chat is its own deployable service
  (its own keys, limits, and failure mode), but lives in the dashboard repo
  because the two change together. Repos follow ownership; services follow
  failure boundaries.
- **Small verification bugs hide in "success" states:** the first deploy
  went red because Azure said `RunningAtMaxScale`, not `Running`. Production
  was fine; the check was too strict. The backend workflow had the same
  latent bug.

**Interview angle:** "How do you make an LLM feature reliable and cheap?"
Shrink and structure the context, compute anything deterministic in code,
evaluate against known answers, and design for provider failure.

---

## 2026-10-08 — Playoff odds v2: making a model better, and proving it

**What happened:** The playoff odds were overconfident early in the season.
After a few games, teams showed 0% or 99%. The model rated teams by their
current point %, and four games is mostly luck. I rebuilt it with an AI
pair-programmer. My part was spotting that the numbers looked wrong,
deciding what "better" meant, and insisting we *measure* it before shipping.

**The concepts, in plain English:**
- **Monte Carlo simulation:** instead of a formula for playoff chances, play
  the rest of the season 10,000 times with weighted dice and count how often
  each team gets in.
- **Regression to the mean:** a coin that lands heads 4 times in a row isn't
  a magic coin. Early on, the model leans on last season and lets this
  season take over as games pile up (blended as "45 pseudo-games").
- **Uncertainty:** we don't *know* how good a team is in October, so each
  simulated season varies every team's strength a little. That's what keeps
  October odds humble instead of 0% / 99%.
- **Calibration:** instead of guessing things like home-ice advantage, we
  measured them from ~4,000 real games: home teams win 54.5% of the time
  between equal teams, 22% of games go to OT, and 32% of those go to a
  shootout.
- **Backtesting:** pretend it's November 1st of a past season, run the model,
  and check it against who actually made the playoffs. Repeat across dates
  and seasons to get a score.
- **Brier score:** "how far off were the probabilities." Lower is better, and
  saying 50% for everyone scores 0.25. The old model scored **0.252** on
  Nov 1, worse than not trying. The new one scored **0.178**.

**Results:** overall Brier 0.152 → 0.129 (15% better); early November 29% better.

**The 30-second interview version:**
> "My dashboard shows playoff odds by simulating the rest of the season
> 10,000 times. Early in the season they were wildly overconfident, because
> a 4-0 team looked like a lock. I rebuilt the model to blend this season's
> results with last season's, so it starts cautious and gets more confident
> as games pile up. To prove it was better, I backtested both versions
> against three past seasons: 15% more accurate overall, and 29% more
> accurate in early November, when the old model was worse than guessing 50/50."

**Follow-up questions to expect:**
- *"Why not use an existing model?"* Building it taught me how they work, and
  I made it measurable so I can keep improving it instead of guessing.
- *"How do you know it's not overfit?"* The game-level numbers were fit on
  the same seasons I tested on, so the absolute score is a bit optimistic.
  The fair comparison is old vs. new under the same conditions, and that gap
  was big. (Admitting a model's limits unprompted is a good look.)
- *"What would you do next?"* Add shot-quality data (expected goals), and
  re-run the calibration script each offseason.

**For front-end interviews,** lead with the product side, not the math:
noticing that 0%/100% in October looked wrong to a user, showing "<1%"
instead of a misleading "0%", hiding stale odds instead of showing last
season's, and measuring before shipping.

**Be honest about AI help.** Don't claim I derived the math. The real skills
were judgment (this looks wrong), framing (what does "better" mean?), and
verification (prove it with a backtest).

---

## 2026-10-08 — A frozen standings day, and my first hotfix

**What happened:** Standings were missing a game for 6 teams. A manual test run
of the daily job at 8:56pm ET wrote that day's snapshot mid-games, and the
script used `ON CONFLICT DO NOTHING`, so the scheduled 2am run's final numbers
were silently skipped. The first run of the day won.

**What I learned:**
- For "one row per day" data, decide **which write should win**. Here it's the
  latest (`DO UPDATE`), so an early or partial run can't freeze the day.
- **Hotfix workflow:** the fix was urgent, but `dev` had an unfinished redesign
  on it. So: branch from `main`, cherry-pick just the fix, PR, merge, deploy,
  then merge `main` back into `dev` so the branches don't drift.
- Manual "test" runs against production data aren't free. That one caused the bug.

---

## 2026-10-08 — Heartbeat monitoring for the daily job

**What happened:** Swapped the Azure "ingestion is stale" alert for a
healthchecks.io heartbeat. The job pings `/start` when it begins, the plain URL
when it succeeds, and `/fail` when it fails.

**What I learned:**
- **Push vs. pull monitoring:** the old alert *looked* for a problem in the
  logs. A heartbeat expects a check-in and alerts when one **doesn't arrive**,
  so it catches the job never running at all. That's the same blind spot as
  the deploy that never ran.
- Monitoring calls should be **best-effort**: if healthchecks.io is down, the
  job still finishes. A ping failure is logged, never raised.
- Treat the ping URL as a secret (stored as a Container Apps secret), since
  anyone holding it could send fake "all good" pings.

---

## 2026-10-08 — Production was silently running July's code

**What happened:** After merging a PR, the frontend deploy finished and I
assumed everything had shipped. It hadn't. The backend's Azure DevOps pipeline
had stopped triggering after July 18, so production was running a three-month-old
backend, and the live scoreboard and game pages returned 404s in production the
whole time. I'd been testing locally, where the new code worked fine.

**Why no alert fired:** I *did* have Azure Monitor alerts: one for crashes and
one for stale ingestion. But they watch the **running app**, and the old app
was perfectly healthy. Nothing watched for "the code on `main` never got
deployed." A stale deploy looks healthy.

**What I learned:**
- Monitoring has layers. "Is the app healthy?" and "is the app running the
  right code?" are different questions, and I only had the first one covered.
- "The deploy finished" isn't the same as "the deploy worked." The new workflow
  only passes if production's `/health` reports the **exact commit** that was
  just deployed.
- A deploy can't report that it never ran. That takes a separate check, so a
  daily GitHub Action compares production's commit to `main` and fails if
  they've drifted.
- **Root cause:** the pipeline still existed (under an Azure DevOps org that
  the Azure Portal doesn't show; it's listed at aex.dev.azure.com/me), but its
  last run was July 18. It never *failed*. GitHub stopped notifying it of new
  commits. It wasn't using the Azure Pipelines GitHub App (no checks ever
  appeared on commits), and by October the repo had zero webhooks, so the
  push webhook or the OAuth connection behind it was most likely removed or
  expired. No runs means no failures, which means no alerts.
- Azure DevOps and the Azure Portal are effectively separate products
  (DevOps grew out of VSTS/TFS). DevOps orgs aren't Azure resources and don't
  show up in a subscription, which is part of why this was easy to forget.
- Watch out for silent schedules: GitHub disables scheduled workflows in public
  repos after 60 days without activity.

**Interview angle:** "Tell me about a production incident." This is a good one:
the detection gap, the root cause, and the fix in three layers (deploy status,
version reporting, drift detection).

---

## 2026-10-08 — Moving CI/CD from Azure DevOps to GitHub Actions (OIDC)

**What happened:** Replaced the broken Azure DevOps pipeline with a GitHub
Actions workflow: test → build → deploy → verify.

**What I learned:**
- **OIDC federated identity:** instead of storing an Azure password in GitHub,
  Azure is configured to trust tokens that GitHub issues for *one specific repo
  and environment* (`repo:nmagera07/nhl-dashboard:environment:production`).
  There's no secret to leak or expire, and expiring credentials are a common
  way pipelines quietly die.
- **Least privilege:** the deploy identity only gets Contributor on one resource
  group, not the whole subscription.
- **One place for everything:** frontend deploy, tests, Dependabot, and now the
  backend deploy all live in GitHub, so a failure is a red ❌ on the commit
  instead of something hidden in a separate tool.
- In single-revision mode, Azure Container Apps keeps the *old* revision serving
  traffic while a new one starts. Checking the public URL right after a deploy
  can return 200 from the old version, so the verify step checks the new
  revision's own health too.

---

## 2026-10-08 — Cutting the Azure bill ~87% (ACR → GHCR)

**What happened:** Pulled actual costs from the Azure Cost Management API.
September was $11.44, and **$10 of it was Azure Container Registry**: just
storing Docker images. Everything else fit in free tiers.

**What I learned:**
- Look at the real bill before guessing. Cost Management showed exactly which
  service cost what.
- **GitHub Container Registry** is free for public images. The repo is already
  public and the image contains no secrets (credentials are injected at runtime),
  so a public image is fine. Azure pulls it anonymously, so there's no
  registry password to manage either.
- **Expand → migrate → contract:** first publish to both registries while still
  deploying from the old one (expand), confirm Azure can pull from the new one,
  switch deploys (migrate), then delete the old registry (contract).
  Production never depended on something that hadn't been verified.
- **Audit what you're actually running.** Cleaning up turned up a *second*,
  empty registry left over from the initial setup (setup tools like
  `az containerapp up` can create resources with random names). It had been
  billing every month with zero images in it. Listing everything in the
  resource group (`az resource list -g ...`) is worth doing now and then.

---

## 2026-10-08 — A plain-text database credential on the API

**What happened:** While cleaning up, I found the API container had the
**write-capable** `DATABASE_URL` set as a plain-text environment variable. The
API never even used it, since it connects with a separate read-only credential.

**What I learned:**
- **Least privilege:** the API should only hold the credential it needs (read-only).
  The ingestion job is the only thing that should be able to write.
- **Secrets vs. env vars:** plain env vars are visible to anyone with read access
  to the resource. Credentials belong in the platform's secret store.
- After a credential has been exposed, **rotate it** too. Removing it isn't enough.
- **Rotation is where mistakes happen.** On the first try, the job's secret got
  the `< >` placeholder brackets from a command template, and my local `.env`
  ended up with the owner URL pasted into both `DATABASE_URL` and
  `API_DATABASE_URL`. What helped:
  - Commands that **read the value from a file** (`dotenv_values(".env")`)
    instead of having me paste it, so I never retype a password.
  - **Verify right after a change** (a test job run, a `SELECT current_user`
    per connection string) instead of finding out at the next scheduled run.
  - The heartbeat monitor emailed about the failed run on its own, which is
    exactly what it's for.

---

## 2026-10-06 — Rosters full of players who'd been cut

**What happened:** Toronto showed 50 players instead of 23. The ingestion
upserted every player on a team's current roster but never removed anyone who'd
left, so training-camp cuts and released players stayed on their old team forever.

**What I learned:**
- An "upsert-only" sync drifts over time. You also have to handle records that
  *disappear* from the source.
- **Soft delete** (`on_roster = false`) instead of deleting rows: player pages,
  career stats, and the leaderboard still need those players.
- Guard against bad upstream data: if the API returns an empty roster, skip
  the cleanup instead of wiping the whole team.
- Database migrations should be **backward compatible**: adding a column with a
  default first means the old code keeps working until the new code deploys.

---

## 2026-10-07 — Box score: reading the API docs (and the actual responses)

**What happened:** The game page looked broken because it asked the NHL's
`/boxscore` endpoint for data it doesn't have. The scoring summary and team
stats live in `/landing` and `/right-rail`.

**What I learned:**
- Inspect real API responses instead of assuming a shape.
- Fetch independent endpoints **in parallel** (about 0.1s for all three).
- **Graceful degradation:** the core endpoint is required, the extras are
  optional, so one feed being down doesn't blank the whole page.

---

## 2026-10-07 — Polling vs. websockets vs. SSE

**Question I asked:** "Is the live score using websockets?"

**Answer:** No, it's **polling**: the page refetches every 30s while a game is
live. React only re-renders what changed, so it *looks* live.

**What I learned:**
- Polling fits here: the NHL API is plain REST (it can't push), traffic is low,
  and stateless requests are easy to scale and cache.
- If many users watched the same game, the better design is for the server to
  poll the NHL once and push to clients with **Server-Sent Events** (one-way,
  simpler than websockets).
- The live endpoints don't touch the database at all, but they do hit the NHL
  API once per viewer. A short server-side cache would make 500 viewers cost
  the same as 1.

**Interview angle:** "When would you use websockets?" Now I have a concrete
answer from my own app.

---

## 2026-10-03 — Treating it like a production app

**What happened:** Set up a `dev` branch for testing locally, with PRs into
`main` (which auto-deploys), branch protection, and required test checks.

**What I learned:**
- Use **merge commits** (not squash) between long-lived branches like
  `dev` → `main`, or the branches drift apart and PRs get messy.
- Grouped Dependabot updates (one weekly PR per ecosystem, targeting `dev`)
  beat a dozen single-package PRs piling up.
- Major dependency bumps can carry hidden requirements: jsdom 30 and vitest 5
  needed Node 22, so CI on Node 20 broke even though tests passed locally.
