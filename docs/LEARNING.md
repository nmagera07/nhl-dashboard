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
- Introduced a `dev` → `main` promotion workflow with branch protection and
  required frontend and backend test checks on every PR.

**Cloud and cost**
- Moved container images from Azure Container Registry to GitHub Container
  Registry with a zero-downtime expand → migrate → contract migration,
  cutting monthly hosting costs by ~87%.
- Consolidated daily data ingestion into a single scheduled Azure Container
  Apps Job with failure isolation between steps and automatic retry.

- Replaced a log-based Azure alert with a heartbeat monitor (healthchecks.io)
  that also detects a scheduled job that never runs, and cut the monthly
  Azure bill from ~$11.44 to ~$0.97.

**AI engineering**
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

- Built an in-browser season simulator by porting the Monte Carlo model to
  JavaScript, validated against the Python original over 10,000 simulated
  seasons (mean gap 0.5 percentage points, the noise floor); runs ~7,000
  full seasons per second client-side at zero server cost.
- Found and fixed a date-boundary bug that silently dropped each day's games
  from the daily playoff simulation (about half the league simulated one game
  short, every day), with a regression test.
- Tested three more model ideas (adjusted xG, strength of schedule,
  goaltending) with held-out backtests and shipped none after showing the
  gains were noise, e.g. goalie performance correlates only r ≈ 0.1 year to year.

**Frontend**
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
