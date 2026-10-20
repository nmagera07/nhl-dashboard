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
- Diagnosed a rising Azure bill with the Cost Management API (free compute grant used up by
  a per-minute container job) and moved the job to an Azure Functions timer, right-sized an
  over-provisioned API (1 GB for ~80 MB of use), and removed cold starts, for a projected
  ~50% lower monthly cost.

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
- Built projected NHL starting goalies (recency-weighted starts, back-to-back rotation,
  current roster) calibrated on 10,112 team-games: the top pick started 66% of the time
  (78% on back-to-back nights), with stated chances accurate within a few points.
- Built a hockey score model (Conway-Maxwell-Poisson goals with a shared component, measured
  tie inflation from score effects, and empty-net goals by lead) from 5,248 games of
  play-by-play. Backtested leave-one-season-out, its puck-line probabilities are calibrated
  within 1-3 points; it's consistent with the win model by solving for the goal margin.
- Built closing-line capture for sports-market benchmarking: an event-driven snapshot near
  game start that batches games into ~2.5 API calls a day, de-margined consensus odds
  (moneyline, spread, total) across 8-9 sportsbooks, and a credit budget guard.
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
- Added schedule fatigue to the game model after a market comparison flagged a big gap: a
  road team on the second night of a back-to-back is worth +0.53 goals/game to its opponent,
  better log loss in all 4 held-out seasons; and showed that predicting the starting goalie
  added nothing measurable, so I didn't build a scraper for confirmed starters.
- Built an expected-goals model from 453,000 NHL shots (logistic regression, 41 features,
  graded on held-out seasons against MoneyPuck's shot-level xG), then replaced MoneyPuck's xG
  in the playoff model with it: as accurate or better (16 of 20 checkpoints, Brier 0.1104 ->
  0.1093) and no longer dependent on a third party.
- Rebuilt team strength as the sum of its players (a WAR-style roster rating) and found that,
  once the players are known, last season's team results add nothing: the best blend gave them
  zero weight. 1.2% lower Brier, better in all 4 backtested seasons, with no new tuning.

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
- Added link preview cards to a single-page app: Open Graph tags, a site-wide card, and
  per-game cards drawn server-side (Pillow) and served by a serverless share page
  (Azure Static Web Apps function) that link previewers can read without JavaScript.
- Re-themed the app with semantic color tokens: about 120 hard-coded colors across 20+
  stylesheets mapped to ~35 roles. That enabled a light/dark mode that follows the system
  until chosen, with no flash of the wrong theme (a CSP-compliant pre-paint script) and
  theme-aware team logos.
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

## 2026-10-19 — The report card: grading ourselves in public

**What:** a `/report-card` page (linked from Bets) for the last 7 days and the season. It shows:
- how often each side's favorite won
- the Brier score for the moneyline, puck line, and total, ours next to the books' (at the
  closing line)
- how the value badges would have done as $100 bets
- the games where we disagreed with the books most, and who was closer

**What I learned:**
- **Pick the metric people can feel, then the one that's right.** "Our favorite won 72%,
  theirs 69%" lands with anyone. The Brier score is the honest one, and it still says the
  books are ahead (0.221 vs. 0.213). The page shows both and highlights whichever side is
  better, even when that's not us.
- **The empty state is a feature.** Zero value badges so far reads as broken unless the page
  says why: a badge needs real disagreement *and* a good price, on purpose.
- **Grade the rules you run today, and say so.** The badges are re-graded with today's rules on
  each game's last line before puck drop, and the page says that, so it doesn't pretend the
  site showed them at the time.
- A tiny one: `0.2135.toFixed(3)` is "0.213", because 0.2135 is really 0.21349999… in binary.

---

## 2026-10-18 — Preview cards: making every shared link an ad

**Why:** "we need users." The cheapest growth lever is making every share look good. A
puckpulse.io link pasted into iMessage, Discord, or Reddit showed as a bare URL.

**The catch with a single-page app:** link previewers read a page's HTML **without running
JavaScript**, and an SPA serves the same `index.html` for every URL. So:
1. **A site-wide card:** Open Graph and Twitter tags in `index.html`, plus a 1200×630 image.
   I designed it in HTML and screenshotted it with Playwright, so the source is editable.
2. **Per-game cards:** a share link `puckpulse.io/g/{id}` that the site *rewrites to a
   serverless function* (Azure Static Web Apps managed functions, free tier). The function
   asks our API for the game's title and description and returns just the preview tags plus
   an instant redirect to the real game page. Crawlers see the game's card; people land on
   the game.
3. **The image itself** is drawn by the API with Pillow: team-colored panels, win chances
   before the game, the score after. Two gotchas:
   - **Fonts:** a slim server image has no fonts, so Inter ships in the repo, with its SIL
     Open Font License.
   - **Logos:** NHL logos are SVG only, which Pillow can't draw, so it uses team colors and
     abbreviations. The darkest teams get an accent border so they don't vanish into the
     background.

**Small things that matter:**
- An **installed PWA's service worker** answers page loads itself, so the app also forwards
  `/g/{id}` to `/games/{id}`.
- A meta refresh needs no script, so the strict Content-Security-Policy doesn't block it.
- The function only accepts a numeric game id; anything else falls back to the site card.

---

## 2026-10-18 — Tonight's lineups, without scraping anyone

**The ask:** "the lines are portrayed weird, and I want current lines that day. But we can't
scrape DailyFaceoff, and AI doesn't play nicely with X."

**What was weird about the old card:**
- Shift charts don't know positions, so lines read "Johnson – Knies – Fantilli" instead of
  LW–C–RW.
- Lines were ranked by minutes together, so a checking line could show as "line 2".
- "15.9 min" meant nothing to most fans.
- No goalies, no scratches.

**The source was already in our stack:** NHL.com posts a "{Away} at {Home} projected
lineups" article for every game a few hours before puck drop. It's on the same NHL content
API our news feed uses, and its address is predictable from the two teams' full names and
the date. All 46 recent articles matched, St. Louis and Montréal included. The X API starts
at $200 a month; this is free and is the league's own.

**Parsing lessons:**
- **Read from the bottom up.** On an 11-forward / 7-D night, the 4th line has two forwards
  and the 7th D is listed alone, so "two names = a D pair" breaks. Instead: the last two
  single names are the goalies (starter first), single names just above them are extra D,
  the last three two-man lines are the pairs, and everything above is forwards.
- **Test on every real example you can get.** Running the parser over all 46 articles found
  both odd formats (the 11F/7D nights and a missing space in "DeAngelo --Mayfield") before
  users did.
- **Keep facts, link the prose.** We show who's on which line and link NHL.com's status
  report instead of copying their writing.

**A free check on our goalie model:** on 10-18, NHL.com's starters matched our projection
for 3 of 4 teams. The miss was Calgary, Cooley instead of Wolf at 71%, which is information
we don't have.

---

## 2026-10-18 — Projected starting goalies (and a what-if I didn't build)

**What:** each team's likely starter and their chance, on the Bets tab ("In net (projected):
Silovs 62% · Blackwood 81%"). NHL teams confirm late, and the NHL's own feed names the
starter only once the game begins, so these are projections from data we already have.

**How:**
- **The training data was already cached.** The goalie in net for a team's first shot
  against is the starter, so 4 seasons of play-by-play gave 10,112 starts.
- **The model:** each goalie gets a weight from his starts this season (each start's weight
  halves every 8 games back), plus a pinch of last season's split. On the second night of a
  back-to-back, last night's starter keeps only 5% of his weight.
- **The grid kept walking to the edge.** The best settings were the most extreme ones I'd
  tried, so I widened twice. That's the data's way of saying something strong: goalies almost
  never start both nights, and this season's starts beat last season's split almost at once.
- **Result:** the top pick started 65.6% of the time (78.0% on back-to-back nights). Log loss
  went from 0.87 to 0.78, and the stated chances matched reality within a few points.
- **Production:** the nightly xG job now records each team's starter, and fills in this
  season's earlier games once. A new daily step stores projections from the current NHL
  roster, which also handles injured reserve and call-ups.

**The what-if I didn't build:** "if the backup starts, COL drops 64% → 59%" sounded great.
But our own 10-13 test found that even the *actual* starter added nothing to win
predictions once back-to-backs were counted. Showing a big swing would have meant
inventing evidence. So the page says that plainly: the starter matters less to who wins
than rest does.

**Interview angle:** knowing when *not* to ship a feature. The evidence said the what-if
would mislead, so I didn't build it.

---

## 2026-10-17 — Light mode, and why it starts with naming colors

**What:** a new "Rink" palette (navy, ice blue, goal-light red) with a matching light theme,
and a sun/moon switch in the header. It follows the phone's setting until you pick one,
then remembers your choice.

**What I learned:**
- **A theme is a set of roles, not a set of colors.** The app had about 120 hard-coded colors
  ("#4ade80", "rgba(59,130,246,.15)") in 20+ files. Each one was really a role: good, bad,
  warning, accent-tint, raised card, shadow. Once every color was a variable named for its
  role, a light theme was just a second set of values for the same names.
- **No flash of the wrong theme.** The theme has to be set before the page paints. That
  usually means an inline script, but the site's Content-Security-Policy blocks inline
  scripts, so it's a tiny file loaded at the top of `<head>`.
- **Images don't follow CSS.** The NHL's team logos come in two versions: `TBL_dark.svg` for
  dark backgrounds and `TBL_light.svg` for light ones. On white, the dark-background Lightning
  logo vanished. The logo helper now picks by theme, and the theme state lives at the app's
  root so a switch re-renders every logo.
- **Contrast flips.** White text on the old blue was fine, but on the brighter ice blue it's
  hard to read, so dark mode uses navy text on blue buttons.

---

## 2026-10-16 — A goal model: from "who wins" to puck lines and totals

**What:** the win model says *who* wins. Bettors also need *by how much* (the puck line,
±1.5) and *how many goals* (the total), so I built a model of the full final score.

The data is 5,248 games (2022-26) from the cached play-by-play: final scores, how each game
ended, regulation goals with empty-netters split out, and xG. It's graded walk-forward and
leave-one-season-out.

**What the data said, one surprise at a time:**
1. **Empty-netters drive the puck line.** A team up one late adds an empty-net goal 0.56
   times a game; up two, 0.69; up three or more, 0.17. My first guess was 0.20, which badly
   undercounted two-goal wins.
2. **Pace barely predicts.** Team ratings predict the margin well (slope ~1.1), but the real
   total moves only 0.43 goals per goal of predicted difference. So the expected total is
   pulled 57% of the way back to the league average.
3. **Goals are less random than Poisson.** Once team strength is known, the variance is
   0.91 of the mean, and the two teams' goals rise and fall slightly together (cov 0.16).
   Modeled with Conway-Maxwell-Poisson (a Poisson with a dispersion knob) plus a shared
   Poisson part.
4. **Hockey ties more than independent scoring says**, 22% to OT vs. 17% predicted. That's
   score effects: the leader sits back, the trailer pushes, and 6-on-5 goals come late.
   Weighting tied regulation scores ×1.37 and one-goal scores ×1.09 fixed it.

Each fix showed up in the calibration table. The favorite covering -1.5 went from 3-5 points
too high to within 1-3 points in every bucket.

**Consistency trick:** in production, the moneyline still comes from the main v2.6 model
(with roster and goalie priors). The goal model supplies the total and then *solves for the
margin* that reproduces that win probability. That way the moneyline, puck line, and total
come from one distribution and can't contradict each other.

**Honest result:** the puck line is well calibrated and beats always-guessing-the-average in
every season. Totals don't beat the average yet. Pace is hard, and the books probably know
things we don't (goalie starts). The next test is against the closing line.

**Interview angle:** "Walk me through improving a model." Start from a simple baseline, read
the calibration table, find the physical cause of each miss (empty nets, score effects),
model it, and confirm out of sample.

---

## 2026-10-16 — The closing line: the market's best guess, and the real test

**What:** a second odds snapshot near puck drop, plus the puck line, total, and best price
on each side. It runs as a 5-minute timer in the notifier function. Once a game is 15
minutes out, one call snapshots every game starting in the next 75 minutes.

**What I learned:**
- **Why the closing line?** The price at puck drop has the most information in it:
  confirmed goalies, late scratches, and the sharp bettors' money. Beating it over
  hundreds of games ("closing line value") is the standard test of whether a model or a
  bettor has an edge, and it doesn't wait on lucky or unlucky results.
- **Batch around a budget.** One call per game would be about 12 a day, 1,000+ credits a
  month on a 500-credit plan. Grouping by start window takes ~2.5 calls a day (checked
  against the real schedule: about 310 credits a month with the morning snapshot). A floor
  guard skips the sportsbooks before the credits run out.
- **Don't take the median of American odds.** -105 and +100 average to -2.5, which is
  nonsense, because the scale jumps from -100 to +100. Convert to probabilities, take the
  median there, and convert back.
- **Books list different lines.** Most say total 6.5, but one might say 6.0. Take the line
  most books offer, and only average prices at that line.

**Interview angle:** "How would you evaluate a prediction model against a market?" Compare
with the closing line, on the same games, with the margin removed, and say how many games
it takes before the difference means anything.

---

## 2026-10-15 — The Azure bill: free grants, cold starts, and the right home for a cron job

**What:** the bill was on pace for ~$25 a month. Two leftover registries ($10) were already
gone, but the free Container Apps compute ran out around Oct 12. The per-minute notifier
job alone used more than the whole grant: 960 container starts a day, about 25 s each,
almost all of it startup. Fixes:
- shrank the API to 0.25 CPU / 0.5 GB (it peaks around 80 MB)
- moved the notifier to an Azure Functions (Flex Consumption) timer
- kept one API replica always up, so no cold starts

**What I learned:**
- **Free tiers are monthly budgets, not features.** Read where the spend goes (the Cost
  Management query API, by resource and meter) rather than trusting the forecast. The
  forecast lagged the real daily jump by days.
- **Match the service to the workload.** A container job is right for the 2 AM ingest
  (minutes of work). For a one-second check every minute, startup dominates the cost.
  A Functions timer keeps a warm worker and bills only the seconds used.
- **Always-on isn't free, but it's cheap.** An idle replica bills CPU at about 1/8 the
  active rate, but memory at the full rate. My first guess ("about even") was wrong; the
  real cost is about $3-5 a month for no cold starts.
- A logging gotcha: our `setup_logging` turns propagation off, so inside Functions the
  notifier's own log lines vanished until they propagated to the root logger.
- **A second one bit in production (10-17).** Importing `market_odds` in the function
  created `logs/` in the read-only code folder. The import failed, and the whole function
  (goal alerts too) was down for 10 minutes mid-game. My package check had imported it
  from a *writable* folder. The lesson is to test in an environment shaped like production:
  now the check runs on a read-only copy, and logging falls back to the console.

---

## 2026-10-15 — "Beat PuckPulse": a pick'em with no accounts

**What:** pick each game's winner before puck drop, one point per right pick, on a public
leaderboard. PuckPulse plays too, picking the model's favorite every game. It's the first
feature where users *save* something.

**Decisions (Nate):**
- *No sign-up:* a display name, and the browser keeps a random key.
- *Public leaderboard first;* friend leagues later.
- *1 point per correct pick.*

**Security for a no-account feature:**
- *Keys:* `pp_` + 24 random bytes. Only the SHA-256 hash is stored, so a database leak can't
  be used to make picks as anyone.
- *Where the key travels:* only in POST bodies, never in URLs (which end up in logs and
  history).
- *Names:* 3-20 characters from a safe set, unique regardless of case, with "PuckPulse" and
  the like reserved, plus a basic filter.
- *Rate limits:* 5 joins per hour per IP, 60 picks per minute.
- *Locking is the server's job:* a pick is refused if the game's state isn't "not started"
  **or** its start time has passed. A cached scoreboard can say FUT for up to a minute after
  puck drop, and the start time closes that gap.

**Fairness:** PuckPulse picks every game, so ranking it by total correct picks would bury
anyone who doesn't play daily. It's a benchmark line instead ("PuckPulse, on every game:
30-15"), and each player gets "vs PuckPulse" on *their* games.

**Not anchoring the user:** PuckPulse's pick (and its percentage) appears only after you pick,
or once the game locks.

**Fast scoring for free:** the goal-alert job already sees every final within a minute, so it
now also writes `game_results`. It's best effort, inside a savepoint, so a missing table can't
break alerts. The nightly grading is the fallback.

## 2026-10-15 — Market view: the model next to the sportsbooks

**Which odds?**
- *Sportsbooks* (DraftKings, FanDuel, BetMGM…) are what bettors recognize ("DET -138").
- *Kalshi* prices are already probabilities.
- *Polymarket* lists NHL games, but $4K-$50K per game is 20-200x thinner than Kalshi.

Shown: the **sportsbook consensus** via The Odds API (free tier: 500 calls a month, and one
call covers every game). Kalshi stays in the comparison log only, because I couldn't verify
its terms for displaying prices elsewhere.

**Turning moneylines into one probability:**
1. *Implied probability:* -150 means 150/250 = 60%, and +130 means 100/230 = 43.5%. They sum
   to 103.5%; the extra 3.5% is the book's margin (the "vig").
2. *Remove the margin per book:* divide each side by the sum (60/103.5 = 58%).
3. *Take the median across books* (9 today), so one outlier book can't move it.

**First real comparison (11 games):** the sportsbooks and Kalshi agreed within about a point on
every game. The markets are consistent with each other, and PuckPulse is the outlier, by up to
6 points, mostly less confident on favorites (VGK, FLA, TBL each about 5 points lower) and
higher on Detroit. Whether that's an edge or a blind spot is what the grading log is for.

**On the page:** collapsed under the game preview's win probability, fetched only when opened.
Two rows (PuckPulse, Sportsbooks), the median moneylines, one sentence on the gap ("PuckPulse
is 5 points higher on DET than the books"), and "For entertainment, 21+... 1-800-GAMBLER".
The phone screenshot caught a ragged layout and the hotline wrapping at a hyphen.

**Small lessons:**
- *Team names never match across APIs:* "St Louis" vs "St. Louis". Compare normalized names
  (no punctuation, no accents).
- *Keys stay out of the transcript:* the script read the key from `.env` and printed only the
  quota headers.

## 2026-10-14 — "I only get one goal alert a game"

**Report (Nate):** goal alerts arrive about once per game; it should be every goal.

**Server first, from the logs:** every send is logged with the event key and the push
service's reply. For PIT @ CHI (8 goals), every goal went out and Google's push service (FCM)
accepted every one (201), plus the final. So nothing was skipped on our side.

**Two real problems found:**
1. *Duplicates:* three goals were sent twice, a minute apart. The NHL posts a goal, then
   corrects its time by a second or two (17:49 to 17:50), and the event key included the
   time, so the corrected goal looked new. The key is now the score the goal made
   (`goal:{game}:{team}:{away}-{home}`), which doesn't change.
2. *One per game on the phone:* all of a game's notifications shared one tag, so each goal
   replaced the last. That was a choice made to avoid clutter. `renotify` asks the phone to
   alert again, but Android can play a replacement quietly, especially rapid updates from one
   app. So it looked like one alert per game. Each goal now gets its own tag, so it's a new
   notification that always alerts. Android groups them under the app.

**Lesson:** *check the server's evidence before guessing at the phone.* The logs ruled out
the notifier in one query and turned up a duplicate bug no one had reported. And *a UX choice
("don't stack") can read as a bug.* The user wanted every goal, visibly.

## 2026-10-14 — Logging the betting market next to the model

**Why first:** before any betting feature faces users, we need to know whether the model has
an edge. The only honest way is to record the market's odds *before* each game, next to our
prediction, and grade both on the same games. It's the same write-it-down-first rule as the
prediction log and the MoneyPuck log.

**Source: Kalshi.** It's a regulated prediction market, and its market data is public: no
account or key needed to read it.
- *One event per game:* `KXNHLGAME-26OCT14DALCOL` (date, away, home), with a "Colorado
  wins" and a "Dallas wins" market, priced in dollars.
- *Implied probability:* the midpoint of each side's bid and ask, normalized to sum to 1.
  Tonight: COL 58.5% (bid 58c, ask 59c, about 1M contracts traded).
- *Team codes:* four differ from the NHL's (LA, NJ, SJ, TB).

**The bug I almost shipped:** testing tonight, Kalshi had Washington at 47.5% while we said
60%. That was a huge gap, until I checked the game: tied 3-3 in the 2nd period. The market
prices the *live* game. The 2 AM job naturally runs before puck drop, but the job retries on
failure, and a late retry would have recorded live prices as "the market's prediction." So
the logger checks the NHL feed and only logs games that haven't started.

**What it logs:** one row per game (implied probability, both sides' bid and ask, volume),
right after our 2 AM predictions. `market_odds.py --report` grades both by Brier score and
counts who was right when we picked different winners.

**Next:** a closing-line snapshot at puck drop, the toughest benchmark there is. Then decide
what to show users, behind a "Market view" toggle.

## 2026-10-14 — Back-to-backs, and the goalie data we didn't need (model v2.6)

**How it started:** Nate saw Kalshi at 60% for Colorado over Dallas while we said 67%. Why
would the market differ? Two things it knows that the model ignored: tired teams (the second
night of a back-to-back) and who starts in net. "Shouldn't we add those?" Yes, if the data
is reliable. Back-to-backs are pure schedule math. Confirmed starters only come from sites
we'd have to scrape.

**Measure before building:** the cached play-by-play for 5,248 games has every team's
dates, and the starting goalie (the goalie in net for the first shot).
- *Home team wins:* 52.7% with both teams rested, **60.4%** when only the road team played
  the night before, 47.1% when only the home team did.
- *#1 goalie starts:* 64% on a normal night, **35%** on the second night of a back-to-back.

**Fit (same frame as calibrate_playoff_model.py: full-season goal differential per game):**

| game model | log loss | home edge | home team tired | road team tired | goalie term |
|---|---|---|---|---|---|
| today's | 0.65134 | +0.238 | | | |
| + back-to-backs | **0.64895** | +0.160 | -0.31 | **+0.53** (for home) | |
| + expected starter | 0.64886 | +0.160 | -0.34 | +0.57 | wrong sign |
| + actual starter | 0.64892 | +0.159 | -0.30 | +0.52 | +0.21, ~nothing |

- *Back-to-backs are real:* better log loss on all 4 held-out seasons, and the road effect is
  steady every season (+0.36 to +0.66).
- *Part of "home ice" was road fatigue:* road teams play the second night about twice as often,
  so the home edge dropped from 0.24 to 0.16 once fatigue had its own term.
- *The starting goalie added nothing,* even the **actual** starter. Our goalie quality ratings
  are too noisy (year-to-year r = 0.16) for "backup vs. starter" to predict much beyond what
  the back-to-back flag already says. So a scraper for confirmed starters wouldn't have paid
  off. *Measuring first saved building the wrong thing.*

**Shipping it (v2.6):**
- `home_margin()`: home ice plus both back-to-back terms, in one place, used by the
  simulation, schedule strength, the prediction log and the scenario tools.
- *Flags in the schedule:* every game carries home_b2b / away_b2b, marked from the schedule,
  so future games have them too. The exported schedule rows grew to
  `[date, home, away, home_b2b, away_b2b]`.
- *Readers:* every reader unpacks with `*rest`, so older saved rows still work.
- *Browser and AI:* the browser simulator and PuckPulse AI's matchup tool read the same
  constants, and the game preview says when a team played last night.
- *Calibration:* calibrate_playoff_model.py now fits the back-to-back terms too, so a rerun
  won't quietly drop them.

**The twist:** in the game that started it, all four teams were on the second night, which
still favors the home team. So v2.6 moved Colorado *up* (66.5% to 68.5%). The fatigue effect
is real across 5,248 games but didn't explain that game's gap with the market. That's
another reason to log the market every night and grade both over hundreds of games.

## 2026-10-14 — The TOI column that passed every test and showed nothing

**Report (Nate):** time on ice never shows on team rosters.

**Cause:** the TOI work three days earlier added the column to the database, the ingest, the
response model, the fixture and the UI, but not to the roster query's `SELECT` list. The
query names its columns one by one, so the API filled `avg_toi_seconds` with its default:
null. The league leaders query had the same gap. The data was there all along (666 of 734
skaters this season).

**Why the tests passed:** the API tests use a fake database that returns whatever row the
test hands it. The fixture row included `avg_toi_seconds`, so the response had it, whatever
the SQL asked for. The tests proved the plumbing *after* the database, not the query itself.

**Fix:** add the column to both queries, plus a test that checks the SQL text for
`s.avg_toi_seconds`.

**Lesson:** *a fake that returns fixed rows can't catch a missing column.* When a field
crosses a hand-written `SELECT`, test the query (or run it against a real database), not just
the response.

**Same session, two smaller ones:**
- *The Playoffs "7d" column:* it compares with odds from at least 7 days back, and the odds
  history began only 7 days earlier, so every row showed "—". It's not a bug, but it looked
  like one, so the column now hides until there's data.
- *The lines card:* it existed only on upcoming game previews, which is hard to find on a
  2-game night. Team pages now have a collapsed "Lines" section too.

## 2026-10-14 — Our own expected goals (model v2.5)

**Why:** the playoff model's main input, xG, came from MoneyPuck's free files. If they
changed their terms or their file format, the model would fall back to a weaker version.
And a real WAR (the next big project) needs shot quality for every shift, which needs our
own xG.

**Data:** NHL play-by-play for 4 seasons, 5,248 games (65 MB gzipped), downloaded once with 4
polite workers. Every unblocked shot has its coordinates, type, the skaters-on-ice code,
which net the home team defends, and the event before it. That's 453,000 shots and 32,000
goals.

**Model:** logistic regression with 41 features:
- distance and angle as flexible piecewise curves
- behind the net
- shot type, and tips or deflections in close
- rebound, and how far the angle swung on the rebound
- rush, puck speed, and the previous event (faceoff, turnover, hit, a shot by the opponent)
- strength (power play, shorthanded, empty net with its own distance slope)
- score state and home ice

Trained with Newton's method in numpy, a dev-only dependency. Production scores shots in
plain Python from a 1.5 KB JSON of coefficients.

**Grading against the best:** MoneyPuck publishes its xG for every shot, so each held-out
season can be compared shot by shot (111,612 of 112,091 shots matched by game, period,
time and shooter).

| held-out season | ours (log loss) | MoneyPuck |
|---|---|---|
| 2022-23 | 0.2304 | 0.2161 |
| 2023-24 | 0.2189 | 0.2148 |
| 2024-25 | **0.2187** | **0.2186** |
| 2025-26 | 0.2263 | 0.2237 |

Close in recent seasons, tied in 2024-25, and well behind in 2022-23, likely because hand
entered shot locations had rink-by-rink bias that MoneyPuck corrects and we don't yet.

**The bug that mattered most:** v0 measured distance with an absolute value, so a shot from
*behind* the net looked like a point-blank shot from the slot. Calibration by distance gave it
away: 0-10 ft was over-predicted by 28%, and beyond 60 ft by 59%. A signed position relative
to the goal line, plus a flexible distance curve, closed more than half the gap to
MoneyPuck. *Check calibration by slices, not just the total.*

**The test that decided it:** shot-level accuracy isn't the goal; team forecasts are. Each
season was scored by an xG model trained on the *other* three, and fed to v2.4:

- Brier 0.1104 with MoneyPuck's xG vs **0.1093** with ours, better at 16 of 20 checkpoints.
- *Read the stats honestly:* the sign test says p = 0.006, but the checkpoints within a season
  share teams. A bootstrap over team-seasons gives a 95% interval of -0.0032 to +0.0010,
  which includes zero. So the claim is "at least as good," not "better."
- *Why could a worse shot model help?* For forecasting, you want the repeatable part of shot
  quality. Ours is simpler and built from the same NHL feed as the goals and standings.

**Shipping it (v2.5):** a nightly step (`ingest_xg.py`) scores each finished game into
`team_game_xg`. The odds use our totals only if every team's scored games match its games
played; otherwise MoneyPuck's xG stands in for the day. The dry run caught one more bug: the
84-game 2026-27 season opened **September 29**, and the first-run search started October 1.

**Lessons:**
- *Grade against the strongest public benchmark,* shot by shot, on seasons the model never saw.
- *The metric that matters is the downstream one.* A slightly worse shot model was an
  equal-or-better forecasting input.
- *A significance test is only as good as its independence assumption.*

## 2026-10-14 — A team is the sum of its players (model v2.4)

**The question:** HockeyStats.com rates teams from player WAR. Could we? We already had
something close: the trade simulator's player values are goals per game over replacement,
calibrated to team goal differential. That's goals above replacement; WAR is roughly the same
divided by 6. So Tier 1 was cheap: rate each team as the sum of its current players.

**The rating:** each skater's value times his expected share of games (last season's games /
82), summed per team. A game has 12 forward and 6 defense slots, so if a team's regulars add
up to more, they're scaled down to fit (some will sit), and empty slots are replacement level
(0). Then centered on the league, plus the existing goalie strength.

**Backtest (4 seasons x 5 dates, as-of data):** three shapes. v2.3 as is, roster only, and
blends of the two.

| | 2022-23 | 2023-24 | 2024-25 | 2025-26 | overall |
|---|---|---|---|---|---|
| v2.3 | 0.0895 | 0.1077 | 0.1018 | 0.1468 | 0.1114 |
| roster rating | **0.0868** | **0.1061** | **0.1014** | **0.1463** | **0.1101** |

- *Better in every season,* with no new tuning: weight 1.0 (values at face value) and the
  same 30-game prior weight as before.
- *The optimum was in the middle of the grid* (1.0 and 1.25 tie, 1.5 is worse), unlike the
  goalie settings that overfit at the edge.
- *Calibration held:* at "90%+" teams made it 98.1% of the time (162 cases).

**The finding bigger than 1.2%:** the best blend put **zero** weight on last season's team xG.
Once you know who's on the roster, how the team did last year adds nothing. "Last season,
adjusted for moves" was a proxy for the players all along.

**Sanity checks before shipping:**
- *Carolina:* rated +0.89 goals/game, higher than anything in the backtest years. The
  breakdown showed depth: twelve full-time forwards with real value, filling exactly 12
  slots. Vancouver had no skater above +0.07.
- *Colorado at 97% in October:* checked against calibration. The top bucket is well
  calibrated, so it stays.

**What's next (Tier 2):** these player values come from Game Score, which credits a player for
his linemates. A third-liner on a great team looks better than he is. A real WAR separates
them by regressing every shift's results on who was on the ice (RAPM), which needs our own xG
model first.

**Interview framing:** "I rebuilt team strength from the bottom up, as the sum of player
values I'd calibrated for a trade simulator. It beat the previous model in all four backtest
seasons, and the interesting result was that last season's team results got zero weight in
the best blend. Once you know the players, the team's history is redundant."

## 2026-10-13 — "I can't scroll up in the chat": three phone bugs in one complaint

**The report (Nate, on his phone):** open the chat, start asking, and you can't scroll back
up to the top. It just hangs there.

**Reproduced first, in an iPhone 13 emulator** (Playwright), with a fake slow stream so it was
repeatable. I scrolled the chat to the top mid-answer, and 300 ms later it was back at the
bottom. Cause: an effect set `scrollTop = scrollHeight` on *every* change to the messages,
and while an answer streams that's dozens of times a second.

**Three fixes:**
1. **Stick to the bottom only if the reader is there.** A scroll listener tracks whether
   you're within 48 px of the bottom. New text follows only then, and sending a question
   always jumps down to show it. That's the standard chat pattern; I'd skipped it.
2. **Keep the sheet above the keyboard.** A bottom sheet `position: fixed; bottom: 0` doesn't
   move when the phone keyboard opens, and iOS shifts the whole page up to keep the text box
   in view, which pushes the top of the chat off the screen. The `visualViewport` API reports
   what's actually visible. A small hook (`useKeepAboveKeyboard`) sets CSS variables so the
   sheet's bottom sits on the keyboard and its height fits what's left.
3. **Don't open the keyboard on open.** The chat auto-focused the text box, which on a
   touchscreen opens the keyboard immediately, covering the suggestions and triggering #2.
   Now it only auto-focuses with a mouse and keyboard (`(hover: none) and (pointer: coarse)`
   means touch).

**Verified:**
- *Emulator:* scrolled up mid-answer, it stays put. At the bottom, it follows. A faked
  keyboard (visible area 330 px of 664) gives a sheet from 12 px to 330 px, fully on screen.
- *Unit tests:* the scroll behavior and the keyboard math.
- *The limit:* a real iOS keyboard can't be emulated, so I faked the browser signal the fix
  listens to.

**Lessons:**
- *Reproduce before fixing.* "Hangs" sounded like a freeze; it was a scroll fight.
- *Mobile web has two viewports.* The layout one doesn't shrink for the keyboard; the visual
  one does. Fixed-position UI near the bottom has to follow the visual one.
- *Auto-focus is a desktop habit.* On a phone it means "open the keyboard now".

## 2026-10-13 — Who's in net: a second null result, and a feature that didn't need a model

**The model question:** the goalie part of the prior weights each goalie by *last* season's
games, so a team whose starter got hurt still counts him all season. The fix seemed
obvious: blend in this season's starts. I pulled every goalie's game log for 4 seasons
(406 NHL API calls, cached) so the backtest could count starts *as of* each checkpoint.

**Result: worse, monotonically.** The more weight on this season's starts, the worse the
Brier (5 → 0.1127, 20 → 0.1122, 80 → 0.1117, never → 0.1114). Half of each rating is this
season's actual goals, and goals against already show who's been in net. A backup who has
been starting is already in the rating, so moving the prior too counts it twice. That's
two null results in a row (aging, then this), and both times the model was already right
for a reason I hadn't spelled out.

**The feature Nate wanted is about the game, not the model:** "show the lines for each
game".
- *Tonight's* projected lines and starting goalies come from sites like DailyFaceoff. That
  means scraping, which their terms don't allow and which breaks when their pages change.
  The NHL API only flags the starting goalie once the game begins.
- *Games in net so far* was already in the NHL's pregame feed (`goalieSeasonStats`).
- *Lines, version 1:* MoneyPuck's `lines.csv`, the most-used 5-on-5 combinations this
  season.
- *Lines, version 2 (shipped):* Nate asked "how do we know these lines are current?", and
  the honest answer was that we didn't. Season totals rank by cumulative ice time, so a line
  broken up after three games could still top the list. The NHL publishes every shift of
  every game. From the last game's shifts, keep the seconds when both teams had exactly 5
  skaters (so power-play units don't blur the lines), add up each pair of teammates' time
  together, and pick the trios and pairs with the most, each player once. On real data it
  gave four clean lines and three pairs, and it showed Washington's new top line
  (Ovechkin–A. Protas–I. Protas), which the season view didn't have at all. The card names
  the game the lines came from.

**What looking at real data caught:** the first version worked in tests and read wrong on
a real game. MoneyPuck drops accents ("Slafkovsk"), Washington has two Protases
("Protas – Protas – Kyrou"), and the top combinations repeated players. The fixes, which
carried into version 2: names from the game's box score (first initial only when
teammates share a last name), and a greedy pick that uses each player once, so it reads
like a lineup. The UI is collapsed under the preview and fetches only when opened.

**Lessons:**
- *Before changing a model input, ask what already carries that information.* This
  season's goals already knew who was in net.
- *Separate "what the user wants to see" from "what the model needs".* The lines were a
  display feature; they didn't need to move the odds to be useful.
- *Check on real data before shipping a UI that shows names.* Fixtures don't have accents
  or brothers.
- *"Is this current?" is a question about the data's definition, not its timestamp.* Data
  refreshed nightly can still describe the wrong period.

## 2026-10-13 — Aging curves: a real effect, the wrong direction (a null result)

**The idea:** a 24-year-old usually improves and a 34-year-old declines, but the prior
treated them the same. Players who stayed on a team cancelled out exactly, so a young core
and an old one looked identical. The plan was to add each team's expected aging to the prior.

**Measuring the curve:** I used the delta method. For every skater with 20+ games in two
straight seasons (4,063 pairs, 2018-19 to 2025-26, birth dates from the NHL stats API's bios
report), I took the change in Game Score per game, grouped it by age, and fit a cubic. It was
the textbook shape: +0.13 at 19, peaking around 25, −0.05 at 34. The fit is reproducible
with `player_values.py --calibrate-aging`.

**The backtest said no:** worse at every weight. 0 → 0.1114, 0.5 → 0.1116, 1.0 → 0.1120,
2.0 → 0.1129. My first theory was double counting: the 0.5 carryover already pulls every
team toward average, and good teams skew old. So I tested aging with *less* generic
shrinkage (carryover 0.6 and 0.7). It still lost at both.

**Why:** the effect wasn't small. It was up to ±0.09 goals/game per team, as big as
goaltending, but it pointed the wrong way. It rated Buffalo the top "aging gainer" in both
2023 and 2024 (missed the playoffs both times), and Edmonton among the oldest decliners
(two straight Finals). The likely cause is **survivor bias**: a young player only forms a
pair if he stayed in the NHL. The ones who had a bad year got sent down and dropped out of
the data, so the curve overstates young players' gains. That's a known weakness of the
delta method, and the backtest caught it before the model did.

**What I kept:** the curve, the fitting command, and the backtest variant, clearly marked as
unused by the model. The model is unchanged (still v2.3). A future fix could count players
who left the league as declines.

**Lessons:**
- *A textbook-shaped curve isn't proof.* It looked exactly right and still made predictions
  worse.
- *When a hypothesis fails, test the obvious rescue once, then stop.* The carryover test was
  a fair second chance. A third would have been searching for a win.
- *Look at the teams it gets wrong.* "Buffalo gains the most two years running" explained
  the failure faster than any summary statistic.
- *Null results are results.* The repo now explains why aging isn't in the model.

**Interview framing:** "I built an aging curve with the delta method, and it had the classic
shape, but adding it made my playoff model worse in a four-season backtest. I tested the
obvious rescue (less generic shrinkage), it still lost, and the teams it got most wrong
pointed to survivor bias in how the curve was measured. So I kept it out of the model and
documented why. Knowing when not to ship is part of the job."

## 2026-10-13 — Analytics without loosening the security work

**Goal:** see whether anyone uses PuckPulse, and which features. Page views alone can't say
whether the AI chat, the season sim, or "Why these odds?" is worth more work.

**Choice: Umami Cloud** (free Hobby plan) over Cloudflare Web Analytics. Both are cookieless
(no consent banner), but only Umami has custom events, and feature usage was the point.

**The security tradeoff, and how I avoided it:** Umami's snippet loads a script from
`cloud.umami.is`. Allowing that domain in `script-src` would undo the strictest line of the
audit's CSP, since any change to their script would run on my site. Instead I read the
script first: it's 4.8 KB, MIT-licensed, and only talks to `gateway.umami.is/api/send`. So
I self-host it as `/stats.js`. `script-src` stays `'self'`, and the only new allowance is
one `connect-src` origin. The cost is that I re-copy it if Umami changes their API.

**Keeping the data clean:** `data-domains` means only puckpulse.io counts, not localhost
or PR previews. `data-do-not-track` respects the browser setting. `track()` is a no-op when
the tracker is blocked, so an ad blocker can't break a feature.

**Events (named for what I'd decide from them):**
- `ai-question`: never the question text, just a count
- `follow-team`
- `goal-alerts-on`
- `season-sim`
- `odds-why`
- `installed-app-open` (PWA vs. browser)
- `app-installed`

**Verified in a browser before shipping:** a headless browser with the production CSP
injected and Umami's endpoint intercepted. The page view, the SPA route change, and a
custom event all fired, with 0 CSP violations from the tracker.

**Interview framing:** "I needed product analytics without weakening a strict CSP. Instead
of allow-listing a third-party script origin, I audited the tracker, self-hosted it, and
allowed only its event endpoint, then verified under the production policy in a headless
browser. Events were chosen for decisions, like whether the AI chat earns more investment,
not for vanity counts."

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
